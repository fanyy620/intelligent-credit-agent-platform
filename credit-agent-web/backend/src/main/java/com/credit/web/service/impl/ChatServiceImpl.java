package com.credit.web.service.impl;

import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.UUID;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import com.credit.web.agent.AgentClient;
import com.credit.web.common.BusinessException;
import com.credit.web.dto.ChatSendRequest;
import com.credit.web.entity.BizChatMessage;
import com.credit.web.entity.BizChatSession;
import com.credit.web.entity.BizRecommendRecord;
import com.credit.web.mapper.BizChatMessageMapper;
import com.credit.web.mapper.BizChatSessionMapper;
import com.credit.web.mapper.BizRecommendRecordMapper;
import com.credit.web.service.ChatService;
import com.credit.web.util.RedisUtil;
import com.fasterxml.jackson.databind.ObjectMapper;

/**
 * 智能对话服务实现。
 *
 * 职责：会话生命周期管理、消息落库、调用 Python Agent、推荐记录归档、
 * Redis 会话上下文（web:chat:ctx:{sessionNo}，与 Agent 侧短期记忆
 * 同实例不同前缀：Agent 用 credit:session:*）。
 * Agent 不可用时降级为友好提示，消息仍落库，不影响其他模块。
 */
@Service
public class ChatServiceImpl implements ChatService {

    private static final Logger log = LoggerFactory.getLogger(ChatServiceImpl.class);
    private static final ObjectMapper MAPPER = new ObjectMapper();
    private static final int CTX_KEEP = 10;          // Redis 上下文保留最近 10 条
    private static final int CTX_SECONDS = 7200;     // 上下文过期 2h

    @Autowired
    private BizChatSessionMapper sessionMapper;

    @Autowired
    private BizChatMessageMapper messageMapper;

    @Autowired
    private BizRecommendRecordMapper recommendMapper;

    @Autowired
    private AgentClient agentClient;

    @Autowired
    private RedisUtil redisUtil;

    @Override
    @Transactional
    @SuppressWarnings("unchecked")
    public Map<String, Object> send(ChatSendRequest request, Long userId, String username) {
        if (request.getMessage() == null || request.getMessage().trim().isEmpty()) {
            throw new BusinessException("消息内容不能为空");
        }
        String message = request.getMessage().trim();

        // 1) 会话：无则新建
        BizChatSession session;
        if (request.getSessionId() == null) {
            session = new BizChatSession();
            session.setSessionNo("S" + UUID.randomUUID().toString().replace("-", "").substring(0, 16));
            session.setUserId(userId);
            session.setCustomerId(request.getCustomerId());
            session.setTitle(message.length() > 20 ? message.substring(0, 20) + "…" : message);
            sessionMapper.insert(session);
        } else {
            session = sessionMapper.selectById(request.getSessionId());
            if (session == null || !session.getUserId().equals(userId)) {
                throw new BusinessException("会话不存在或无权访问");
            }
            if (request.getCustomerId() != null && session.getCustomerId() == null) {
                session.setCustomerId(request.getCustomerId());
            }
        }

        // 2) 客户消息落库
        saveMessage(session.getId(), "user", message, "", "");

        // 3) 调用 Python Agent（降级返回 available=false）
        Map<String, Object> agentData = agentClient.chat(
                session.getSessionNo(), "u" + userId, message);
        boolean available = Boolean.TRUE.equals(agentData.get("available"));
        String reply = String.valueOf(agentData.getOrDefault("reply", ""));
        String intent = String.valueOf(agentData.getOrDefault("intent", ""));
        String intentZh = String.valueOf(agentData.getOrDefault("intent_zh", ""));

        // 4) 助手消息落库（降级回复同样落库，保证会话完整）
        saveMessage(session.getId(), "assistant", reply, intent, intentZh);

        // 5) 推荐记录归档（含四维评分明细 JSON）
        Object recsObj = agentData.get("recommendations");
        if (available && recsObj instanceof List && !((List<Object>) recsObj).isEmpty()) {
            try {
                List<Map<String, Object>> recs = (List<Map<String, Object>>) recsObj;
                Map<String, Object> topProduct = (Map<String, Object>) recs.get(0).get("product");
                BizRecommendRecord record = new BizRecommendRecord();
                record.setSessionId(session.getId());
                record.setCustomerId(session.getCustomerId());
                record.setUserId(userId);
                record.setMessage(message);
                record.setTopProduct(String.valueOf(topProduct.get("name")));
                Map<String, Object> payload = new HashMap<String, Object>();
                payload.put("slots", agentData.get("slots"));
                payload.put("recommendations", recs);
                record.setResultJson(MAPPER.writeValueAsString(payload));
                recommendMapper.insert(record);
            } catch (Exception e) {
                log.warn("推荐记录归档失败（不影响主流程）: {}", e.getMessage());
            }
        }

        // 6) Redis 会话上下文（最近 N 条，供横向排查与将来上下文增强）
        updateRedisContext(session.getSessionNo(), message, reply);

        // 7) 会话活跃时间
        sessionMapper.touchUpdateTime(session.getId());

        // 8) 组装响应
        Map<String, Object> result = new HashMap<String, Object>();
        result.put("session_id", session.getId());
        result.put("session_no", session.getSessionNo());
        result.put("reply", reply);
        result.put("intent", intent);
        result.put("intent_zh", intentZh);
        result.put("recommendations", recsObj);
        result.put("compliance", agentData.get("compliance"));
        result.put("memory_used", agentData.get("memory_used"));
        result.put("agent_available", available);
        return result;
    }

    @Override
    public List<BizChatSession> listSessions(Long userId, int limit) {
        return sessionMapper.selectByUserId(userId, 0, Math.min(Math.max(limit, 1), 100));
    }

    @Override
    public List<BizChatMessage> listMessages(Long sessionId, Long userId) {
        BizChatSession session = sessionMapper.selectById(sessionId);
        if (session == null || !session.getUserId().equals(userId)) {
            throw new BusinessException("会话不存在或无权访问");
        }
        return messageMapper.selectBySessionId(sessionId);
    }

    private void saveMessage(Long sessionId, String role, String content,
                             String intent, String intentZh) {
        BizChatMessage msg = new BizChatMessage();
        msg.setSessionId(sessionId);
        msg.setRole(role);
        msg.setContent(content);
        msg.setIntent(intent);
        msg.setIntentZh(intentZh);
        messageMapper.insert(msg);
    }

    @SuppressWarnings("unchecked")
    private void updateRedisContext(String sessionNo, String userMsg, String assistantMsg) {
        String key = "web:chat:ctx:" + sessionNo;
        try {
            List<Map<String, String>> ctx = new ArrayList<Map<String, String>>();
            String old = redisUtil.get(key);
            if (old != null) {
                ctx = MAPPER.readValue(old, List.class);
            }
            Map<String, String> u = new HashMap<String, String>();
            u.put("role", "user");
            u.put("content", userMsg);
            Map<String, String> a = new HashMap<String, String>();
            a.put("role", "assistant");
            a.put("content", assistantMsg);
            ctx.add(u);
            ctx.add(a);
            if (ctx.size() > CTX_KEEP) {
                ctx = new ArrayList<Map<String, String>>(ctx.subList(ctx.size() - CTX_KEEP, ctx.size()));
            }
            redisUtil.set(key, MAPPER.writeValueAsString(ctx), CTX_SECONDS);
        } catch (Exception e) {
            log.warn("Redis 会话上下文更新失败（不影响主流程）: {}", e.getMessage());
        }
    }
}
