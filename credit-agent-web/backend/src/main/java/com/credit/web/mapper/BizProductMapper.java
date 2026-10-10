package com.credit.web.mapper;

import java.util.List;

import org.apache.ibatis.annotations.Param;

import com.credit.web.entity.BizProduct;

/** 信贷产品 Mapper */
public interface BizProductMapper {

    List<BizProduct> selectAllOnSale();

    BizProduct selectById(@Param("id") Long id);

    int insert(BizProduct product);

    int updateById(BizProduct product);

    int deleteById(@Param("id") Long id);
}
