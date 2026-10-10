package com.credit.web.service;

import com.credit.web.common.PageResult;
import com.credit.web.entity.BizRecommendRecord;

/** 推荐记录服务 */
public interface RecommendService {

    PageResult<BizRecommendRecord> page(Long customerId, int pageNum, int pageSize);
}
