package com.credit.web.entity;

import java.io.Serializable;
import java.util.Date;

/** 营销文案与合规审核记录（biz_copy_record） */
public class BizCopyRecord implements Serializable {

    private static final long serialVersionUID = 1L;

    private Long id;
    private Long userId;
    private Long customerId;
    private String productId;
    private String productName;
    private String channel;
    private String template;
    private String content;
    private Integer compliant;
    private String hitRules;
    private String conclusion;
    private Date createTime;

    /** 关联字段（非表列） */
    private String username;

    public Long getId() { return id; }
    public void setId(Long id) { this.id = id; }
    public Long getUserId() { return userId; }
    public void setUserId(Long userId) { this.userId = userId; }
    public Long getCustomerId() { return customerId; }
    public void setCustomerId(Long customerId) { this.customerId = customerId; }
    public String getProductId() { return productId; }
    public void setProductId(String productId) { this.productId = productId; }
    public String getProductName() { return productName; }
    public void setProductName(String productName) { this.productName = productName; }
    public String getChannel() { return channel; }
    public void setChannel(String channel) { this.channel = channel; }
    public String getTemplate() { return template; }
    public void setTemplate(String template) { this.template = template; }
    public String getContent() { return content; }
    public void setContent(String content) { this.content = content; }
    public Integer getCompliant() { return compliant; }
    public void setCompliant(Integer compliant) { this.compliant = compliant; }
    public String getHitRules() { return hitRules; }
    public void setHitRules(String hitRules) { this.hitRules = hitRules; }
    public String getConclusion() { return conclusion; }
    public void setConclusion(String conclusion) { this.conclusion = conclusion; }
    public Date getCreateTime() { return createTime; }
    public void setCreateTime(Date createTime) { this.createTime = createTime; }
    public String getUsername() { return username; }
    public void setUsername(String username) { this.username = username; }
}
