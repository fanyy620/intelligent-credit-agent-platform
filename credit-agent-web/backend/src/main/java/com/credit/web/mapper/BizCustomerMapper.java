package com.credit.web.mapper;

import java.util.List;

import org.apache.ibatis.annotations.Param;

import com.credit.web.entity.BizCustomer;

/** 信贷客户 Mapper */
public interface BizCustomerMapper {

    long countByCondition(@Param("name") String name,
                          @Param("phone") String phone,
                          @Param("occupation") String occupation);

    List<BizCustomer> selectPageByCondition(@Param("name") String name,
                                            @Param("phone") String phone,
                                            @Param("occupation") String occupation,
                                            @Param("offset") int offset,
                                            @Param("limit") int limit);

    BizCustomer selectById(@Param("id") Long id);

    int insert(BizCustomer customer);

    int updateById(BizCustomer customer);

    int deleteById(@Param("id") Long id);
}
