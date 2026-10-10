package com.credit.web.service.impl;

import java.util.List;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import com.credit.web.common.BusinessException;
import com.credit.web.common.PageResult;
import com.credit.web.entity.BizCustomer;
import com.credit.web.mapper.BizCustomerMapper;
import com.credit.web.service.CustomerService;

/** 客户管理服务实现 */
@Service
public class CustomerServiceImpl implements CustomerService {

    @Autowired
    private BizCustomerMapper bizCustomerMapper;

    @Override
    public PageResult<BizCustomer> page(String name, String phone, String occupation,
                                        int pageNum, int pageSize) {
        pageNum = Math.max(pageNum, 1);
        pageSize = Math.min(Math.max(pageSize, 1), 100);
        long total = bizCustomerMapper.countByCondition(name, phone, occupation);
        List<BizCustomer> list = bizCustomerMapper.selectPageByCondition(
                name, phone, occupation, PageResult.offset(pageNum, pageSize), pageSize);
        return new PageResult<BizCustomer>(total, pageNum, pageSize, list);
    }

    @Override
    public BizCustomer getById(Long id) {
        BizCustomer customer = bizCustomerMapper.selectById(id);
        if (customer == null) {
            throw new BusinessException("客户不存在: id=" + id);
        }
        return customer;
    }

    @Override
    @Transactional
    public BizCustomer create(BizCustomer customer, String operator) {
        if (customer.getName() == null || customer.getName().trim().isEmpty()) {
            throw new BusinessException("客户姓名不能为空");
        }
        customer.setCreateBy(operator);
        bizCustomerMapper.insert(customer);
        return customer;
    }

    @Override
    @Transactional
    public int update(BizCustomer customer) {
        if (customer.getId() == null) {
            throw new BusinessException("缺少客户ID");
        }
        int rows = bizCustomerMapper.updateById(customer);
        if (rows == 0) {
            throw new BusinessException("客户不存在: id=" + customer.getId());
        }
        return rows;
    }

    @Override
    @Transactional
    public int delete(Long id) {
        int rows = bizCustomerMapper.deleteById(id);
        if (rows == 0) {
            throw new BusinessException("客户不存在: id=" + id);
        }
        return rows;
    }
}
