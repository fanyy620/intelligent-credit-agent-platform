package com.credit.web.entity;

import java.io.Serializable;
import java.util.Date;

/** 智能助理对话会话（biz_chat_session） */
public class BizChatSession implements Serializable {

    private static final long serialVersionUID = 1L;

    private Long id;
    private String sessionNo;
    private Long userId;
    private Long customerId;
    private String title;
    private Date createTime;
    private Date updateTime;

    /** 关联字段（非表列）：客户姓名 */
    private String customerName;

    public Long getId() { return id; }
    public void setId(Long id) { this.id = id; }
    public String getSessionNo() { return sessionNo; }
    public void setSessionNo(String sessionNo) { this.sessionNo = sessionNo; }
    public Long getUserId() { return userId; }
    public void setUserId(Long userId) { this.userId = userId; }
    public Long getCustomerId() { return customerId; }
    public void setCustomerId(Long customerId) { this.customerId = customerId; }
    public String getTitle() { return title; }
    public void setTitle(String title) { this.title = title; }
    public Date getCreateTime() { return createTime; }
    public void setCreateTime(Date createTime) { this.createTime = createTime; }
    public Date getUpdateTime() { return updateTime; }
    public void setUpdateTime(Date updateTime) { this.updateTime = updateTime; }
    public String getCustomerName() { return customerName; }
    public void setCustomerName(String customerName) { this.customerName = customerName; }
}
