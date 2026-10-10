package com.credit.web.mapper;

import java.util.List;

import org.apache.ibatis.annotations.Param;

import com.credit.web.entity.BizRecommendRecord;

/** 授信推荐记录 Mapper */
public interface BizRecommendRecordMapper {

    int insert(BizRecommendRecord record);

    long countByCondition(@Param("customerId") Long customerId);

    List<BizRecommendRecord> selectPageByCondition(@Param("customerId") Long customerId,
                                                   @Param("offset") int offset,
                                                   @Param("limit") int limit);
}
