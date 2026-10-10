package com.credit.web.entity;

import java.io.Serializable;
import java.math.BigDecimal;
import java.util.Date;

/** 信贷产品（biz_product，字段与 Agent 产品库 products.yaml 对齐） */
public class BizProduct implements Serializable {

    private static final long serialVersionUID = 1L;

    private Long id;
    private String productCode;
    private String name;
    private String category;
    private BigDecimal minAmount;
    private BigDecimal maxAmount;
    private Integer minTermMonths;
    private Integer maxTermMonths;
    private BigDecimal annualRateMin;
    private BigDecimal annualRateMax;
    private BigDecimal approvalHours;
    private Integer minAge;
    private Integer maxAge;
    private BigDecimal minMonthlyIncome;
    private Integer minCreditScore;
    private String allowedPurposes;
    private String tags;
    private String description;
    private Integer status;
    private Date createTime;
    private Date updateTime;

    public Long getId() { return id; }
    public void setId(Long id) { this.id = id; }
    public String getProductCode() { return productCode; }
    public void setProductCode(String productCode) { this.productCode = productCode; }
    public String getName() { return name; }
    public void setName(String name) { this.name = name; }
    public String getCategory() { return category; }
    public void setCategory(String category) { this.category = category; }
    public BigDecimal getMinAmount() { return minAmount; }
    public void setMinAmount(BigDecimal minAmount) { this.minAmount = minAmount; }
    public BigDecimal getMaxAmount() { return maxAmount; }
    public void setMaxAmount(BigDecimal maxAmount) { this.maxAmount = maxAmount; }
    public Integer getMinTermMonths() { return minTermMonths; }
    public void setMinTermMonths(Integer minTermMonths) { this.minTermMonths = minTermMonths; }
    public Integer getMaxTermMonths() { return maxTermMonths; }
    public void setMaxTermMonths(Integer maxTermMonths) { this.maxTermMonths = maxTermMonths; }
    public BigDecimal getAnnualRateMin() { return annualRateMin; }
    public void setAnnualRateMin(BigDecimal annualRateMin) { this.annualRateMin = annualRateMin; }
    public BigDecimal getAnnualRateMax() { return annualRateMax; }
    public void setAnnualRateMax(BigDecimal annualRateMax) { this.annualRateMax = annualRateMax; }
    public BigDecimal getApprovalHours() { return approvalHours; }
    public void setApprovalHours(BigDecimal approvalHours) { this.approvalHours = approvalHours; }
    public Integer getMinAge() { return minAge; }
    public void setMinAge(Integer minAge) { this.minAge = minAge; }
    public Integer getMaxAge() { return maxAge; }
    public void setMaxAge(Integer maxAge) { this.maxAge = maxAge; }
    public BigDecimal getMinMonthlyIncome() { return minMonthlyIncome; }
    public void setMinMonthlyIncome(BigDecimal minMonthlyIncome) { this.minMonthlyIncome = minMonthlyIncome; }
    public Integer getMinCreditScore() { return minCreditScore; }
    public void setMinCreditScore(Integer minCreditScore) { this.minCreditScore = minCreditScore; }
    public String getAllowedPurposes() { return allowedPurposes; }
    public void setAllowedPurposes(String allowedPurposes) { this.allowedPurposes = allowedPurposes; }
    public String getTags() { return tags; }
    public void setTags(String tags) { this.tags = tags; }
    public String getDescription() { return description; }
    public void setDescription(String description) { this.description = description; }
    public Integer getStatus() { return status; }
    public void setStatus(Integer status) { this.status = status; }
    public Date getCreateTime() { return createTime; }
    public void setCreateTime(Date createTime) { this.createTime = createTime; }
    public Date getUpdateTime() { return updateTime; }
    public void setUpdateTime(Date updateTime) { this.updateTime = updateTime; }
}
