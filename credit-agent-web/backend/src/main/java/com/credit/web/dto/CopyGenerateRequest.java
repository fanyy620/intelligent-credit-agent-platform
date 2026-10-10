package com.credit.web.dto;

import java.io.Serializable;

/** 营销文案生成请求体 */
public class CopyGenerateRequest implements Serializable {

    private static final long serialVersionUID = 1L;

    /** 产品编码（Agent 产品库 id，如 xinxiangdai） */
    private String productId;
    /** 投放渠道：朋友圈/短信/海报 */
    private String channel;
    /** 关联客户（可选） */
    private Long customerId;

    public String getProductId() { return productId; }
    public void setProductId(String productId) { this.productId = productId; }
    public String getChannel() { return channel; }
    public void setChannel(String channel) { this.channel = channel; }
    public Long getCustomerId() { return customerId; }
    public void setCustomerId(Long customerId) { this.customerId = customerId; }
}
