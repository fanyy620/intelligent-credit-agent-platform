package com.credit.web.service.impl;

import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import com.credit.web.agent.AgentClient;
import com.credit.web.common.BusinessException;
import com.credit.web.common.PageResult;
import com.credit.web.dto.CopyGenerateRequest;
import com.credit.web.entity.BizCopyRecord;
import com.credit.web.mapper.BizCopyRecordMapper;
import com.credit.web.service.CopyService;
import com.fasterxml.jackson.databind.ObjectMapper;

/**
 * 营销文案与合规服务实现。
 * 调用 Agent 的模板填充端点（数值由结构化数据渲染，杜绝幻觉），
 * 合规结论与命中规则一并落库，支持“仅看违规”过滤。
 */
@Service
public class CopyServiceImpl implements CopyService {

    private static final ObjectMapper MAPPER = new ObjectMapper();

    @Autowired
    private BizCopyRecordMapper copyRecordMapper;

    @Autowired
    private AgentClient agentClient;

    @Override
    @Transactional
    @SuppressWarnings("unchecked")
    public Map<String, Object> generate(CopyGenerateRequest request, Long userId) {
        if (request.getProductId() == null || request.getProductId().trim().isEmpty()) {
            throw new BusinessException("产品编码不能为空");
        }
        String channel = request.getChannel() == null || request.getChannel().trim().isEmpty()
                ? "朋友圈" : request.getChannel().trim();

        Map<String, Object> agentData = agentClient.generateCopy(
                "u" + userId, request.getProductId().trim(), channel);
        if (!Boolean.TRUE.equals(agentData.get("available"))) {
            throw new BusinessException("智能文案服务暂时不可用，请确认 Python Agent 已启动后重试");
        }

        Map<String, Object> compliance = (Map<String, Object>) agentData.get("compliance");
        boolean compliant = compliance != null && Boolean.TRUE.equals(compliance.get("compliant"));

        // 命中规则汇总（正则 + 语义）
        List<String> hits = new ArrayList<String>();
        if (compliance != null) {
            Object regexHits = compliance.get("regex_hits");
            if (regexHits instanceof List) {
                for (Object h : (List<Object>) regexHits) {
                    if (h instanceof Map) {
                        hits.add(String.valueOf(((Map<String, Object>) h).get("rule_name")));
                    }
                }
            }
            Object semantic = compliance.get("semantic");
            if (semantic instanceof Map) {
                Object semHits = ((Map<String, Object>) semantic).get("hits");
                if (semHits instanceof List) {
                    for (Object h : (List<Object>) semHits) {
                        if (h instanceof Map) {
                            hits.add("语义相似: " + ((Map<String, Object>) h).get("exemplar"));
                        }
                    }
                }
            }
        }

        BizCopyRecord record = new BizCopyRecord();
        record.setUserId(userId);
        record.setCustomerId(request.getCustomerId());
        record.setProductId(String.valueOf(agentData.get("product_id")));
        record.setProductName(String.valueOf(agentData.get("product_name")));
        record.setChannel(channel);
        record.setTemplate(String.valueOf(agentData.getOrDefault("template", "")));
        record.setContent(String.valueOf(agentData.getOrDefault("text", "")));
        record.setCompliant(compliant ? 1 : 0);
        try {
            record.setHitRules(MAPPER.writeValueAsString(hits));
        } catch (Exception e) {
            record.setHitRules("[]");
        }
        record.setConclusion(compliant
                ? "双重风控（正则+语义）审核通过"
                : "命中 " + hits.size() + " 条违规规则，建议修改后重新生成");
        copyRecordMapper.insert(record);

        Map<String, Object> result = new HashMap<String, Object>();
        result.put("record", record);
        result.put("compliance", compliance);
        result.put("template_blocked", agentData.get("template_blocked"));
        return result;
    }

    @Override
    public PageResult<BizCopyRecord> page(boolean onlyViolation, int pageNum, int pageSize) {
        pageNum = Math.max(pageNum, 1);
        pageSize = Math.min(Math.max(pageSize, 1), 100);
        long total = copyRecordMapper.countByCondition(onlyViolation);
        List<BizCopyRecord> list = copyRecordMapper.selectPageByCondition(
                onlyViolation, PageResult.offset(pageNum, pageSize), pageSize);
        return new PageResult<BizCopyRecord>(total, pageNum, pageSize, list);
    }
}
