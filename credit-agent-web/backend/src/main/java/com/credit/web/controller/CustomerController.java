package com.credit.web.controller;

import javax.servlet.http.HttpServletRequest;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.stereotype.Controller;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestMethod;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.ResponseBody;

import com.credit.web.common.PageResult;
import com.credit.web.common.Result;
import com.credit.web.entity.BizCustomer;
import com.credit.web.service.CustomerService;
import com.credit.web.util.LoginContext;

/** 客户管理控制器：CRUD + 分页 */
@Controller
@RequestMapping("/customer")
public class CustomerController {

    @Autowired
    private CustomerService customerService;

    @ResponseBody
    @RequestMapping(value = "/page", method = RequestMethod.GET)
    public Result<PageResult<BizCustomer>> page(
            @RequestParam(required = false) String name,
            @RequestParam(required = false) String phone,
            @RequestParam(required = false) String occupation,
            @RequestParam(defaultValue = "1") int pageNum,
            @RequestParam(defaultValue = "10") int pageSize) {
        return Result.ok(customerService.page(name, phone, occupation, pageNum, pageSize));
    }

    @ResponseBody
    @RequestMapping(value = "/{id}", method = RequestMethod.GET)
    public Result<BizCustomer> detail(@PathVariable Long id) {
        return Result.ok(customerService.getById(id));
    }

    @ResponseBody
    @RequestMapping(value = "", method = RequestMethod.POST)
    public Result<BizCustomer> create(@RequestBody BizCustomer customer,
                                      HttpServletRequest request) {
        return Result.ok("新增成功",
                customerService.create(customer, LoginContext.currentUsername(request)));
    }

    @ResponseBody
    @RequestMapping(value = "/{id}", method = RequestMethod.PUT)
    public Result<Integer> update(@PathVariable Long id, @RequestBody BizCustomer customer) {
        customer.setId(id);
        return Result.ok("更新成功", customerService.update(customer));
    }

    @ResponseBody
    @RequestMapping(value = "/{id}", method = RequestMethod.DELETE)
    public Result<Integer> delete(@PathVariable Long id) {
        return Result.ok("删除成功", customerService.delete(id));
    }
}
