package com.credit.web.dto;

import java.io.Serializable;

/** 对话发送请求体 */
public class ChatSendRequest implements Serializable {

    private static final long serialVersionUID = 1L;

    /** 会话ID（首次为空则新建会话） */
    private Long sessionId;
    /** 关联客户（可选，用于推荐记录归属） */
    private Long customerId;
    /** 消息内容 */
    private String message;

    public Long getSessionId() { return sessionId; }
    public void setSessionId(Long sessionId) { this.sessionId = sessionId; }
    public Long getCustomerId() { return customerId; }
    public void setCustomerId(Long customerId) { this.customerId = customerId; }
    public String getMessage() { return message; }
    public void setMessage(String message) { this.message = message; }
}
