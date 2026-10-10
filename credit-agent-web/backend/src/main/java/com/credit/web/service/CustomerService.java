package com.credit.web.service;

import com.credit.web.common.PageResult;
import com.credit.web.entity.BizCustomer;

/** 客户管理服务 */
public interface CustomerService {

    PageResult<BizCustomer> page(String name, String phone, String occupation,
                                 int pageNum, int pageSize);

    BizCustomer getById(Long id);

    BizCustomer create(BizCustomer customer, String operator);

    int update(BizCustomer customer);

    int delete(Long id);
}
