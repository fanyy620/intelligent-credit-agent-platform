package com.credit.web.service.impl;

import java.util.List;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.stereotype.Service;

import com.credit.web.common.PageResult;
import com.credit.web.entity.BizRecommendRecord;
import com.credit.web.mapper.BizRecommendRecordMapper;
import com.credit.web.service.RecommendService;

/** 推荐记录服务实现 */
@Service
public class RecommendServiceImpl implements RecommendService {

    @Autowired
    private BizRecommendRecordMapper recommendRecordMapper;

    @Override
    public PageResult<BizRecommendRecord> page(Long customerId, int pageNum, int pageSize) {
        pageNum = Math.max(pageNum, 1);
        pageSize = Math.min(Math.max(pageSize, 1), 100);
        long total = recommendRecordMapper.countByCondition(customerId);
        List<BizRecommendRecord> list = recommendRecordMapper.selectPageByCondition(
                customerId, PageResult.offset(pageNum, pageSize), pageSize);
        return new PageResult<BizRecommendRecord>(total, pageNum, pageSize, list);
    }
}
