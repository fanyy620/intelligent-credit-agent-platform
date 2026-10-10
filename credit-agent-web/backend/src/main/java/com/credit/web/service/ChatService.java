package com.credit.web.service;

import java.util.List;
import java.util.Map;

import com.credit.web.dto.ChatSendRequest;
import com.credit.web.entity.BizChatMessage;
import com.credit.web.entity.BizChatSession;

/** 智能对话服务 */
public interface ChatService {

    /** 发送消息：调 Agent → 落库消息/推荐记录 → Redis 上下文 */
    Map<String, Object> send(ChatSendRequest request, Long userId, String username);

    List<BizChatSession> listSessions(Long userId, int limit);

    List<BizChatMessage> listMessages(Long sessionId, Long userId);
}
