package com.credit.web.controller;

import java.util.List;

import javax.servlet.http.HttpServletRequest;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.stereotype.Controller;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestMethod;
import org.springframework.web.bind.annotation.ResponseBody;

import com.credit.web.common.Result;
import com.credit.web.entity.BizProduct;
import com.credit.web.service.ProductService;
import com.credit.web.util.LoginContext;

/** 信贷产品控制器：列表全员可见，增删改仅管理员 */
@Controller
@RequestMapping("/product")
public class ProductController {

    @Autowired
    private ProductService productService;

    @ResponseBody
    @RequestMapping(value = "/list", method = RequestMethod.GET)
    public Result<List<BizProduct>> list() {
        return Result.ok(productService.listOnSale());
    }

    @ResponseBody
    @RequestMapping(value = "", method = RequestMethod.POST)
    public Result<BizProduct> create(@RequestBody BizProduct product,
                                     HttpServletRequest request) {
        LoginContext.requireAdmin(request);
        return Result.ok("新增成功", productService.create(product));
    }

    @ResponseBody
    @RequestMapping(value = "/{id}", method = RequestMethod.PUT)
    public Result<Integer> update(@PathVariable Long id, @RequestBody BizProduct product,
                                  HttpServletRequest request) {
        LoginContext.requireAdmin(request);
        product.setId(id);
        return Result.ok("更新成功", productService.update(product));
    }

    @ResponseBody
    @RequestMapping(value = "/{id}", method = RequestMethod.DELETE)
    public Result<Integer> delete(@PathVariable Long id, HttpServletRequest request) {
        LoginContext.requireAdmin(request);
        return Result.ok("删除成功", productService.delete(id));
    }
}
