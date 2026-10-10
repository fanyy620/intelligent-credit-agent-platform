package com.credit.web.entity;

import java.io.Serializable;
import java.util.Date;

/** 授信推荐记录（biz_recommend_record） */
public class BizRecommendRecord implements Serializable {

    private static final long serialVersionUID = 1L;

    private Long id;
    private Long sessionId;
    private Long customerId;
    private Long userId;
    private String message;
    private String topProduct;
    private String resultJson;
    private Date createTime;

    /** 关联字段（非表列） */
    private String customerName;
    private String username;

    public Long getId() { return id; }
    public void setId(Long id) { this.id = id; }
    public Long getSessionId() { return sessionId; }
    public void setSessionId(Long sessionId) { this.sessionId = sessionId; }
    public Long getCustomerId() { return customerId; }
    public void setCustomerId(Long customerId) { this.customerId = customerId; }
    public Long getUserId() { return userId; }
    public void setUserId(Long userId) { this.userId = userId; }
    public String getMessage() { return message; }
    public void setMessage(String message) { this.message = message; }
    public String getTopProduct() { return topProduct; }
    public void setTopProduct(String topProduct) { this.topProduct = topProduct; }
    public String getResultJson() { return resultJson; }
    public void setResultJson(String resultJson) { this.resultJson = resultJson; }
    public Date getCreateTime() { return createTime; }
    public void setCreateTime(Date createTime) { this.createTime = createTime; }
    public String getCustomerName() { return customerName; }
    public void setCustomerName(String customerName) { this.customerName = customerName; }
    public String getUsername() { return username; }
    public void setUsername(String username) { this.username = username; }
}
