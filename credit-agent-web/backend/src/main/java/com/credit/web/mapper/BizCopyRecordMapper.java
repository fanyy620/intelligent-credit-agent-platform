package com.credit.web.mapper;

import java.util.List;

import org.apache.ibatis.annotations.Param;

import com.credit.web.entity.BizCopyRecord;

/** 营销文案与合规审核记录 Mapper */
public interface BizCopyRecordMapper {

    int insert(BizCopyRecord record);

    long countByCondition(@Param("onlyViolation") Boolean onlyViolation);

    List<BizCopyRecord> selectPageByCondition(@Param("onlyViolation") Boolean onlyViolation,
                                              @Param("offset") int offset,
                                              @Param("limit") int limit);
}
