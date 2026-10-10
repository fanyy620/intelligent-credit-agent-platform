package com.credit.web.controller;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.stereotype.Controller;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestMethod;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.ResponseBody;

import com.credit.web.common.PageResult;
import com.credit.web.common.Result;
import com.credit.web.entity.BizRecommendRecord;
import com.credit.web.service.RecommendService;

/** 推荐记录控制器：分页查询，支持按客户过滤 */
@Controller
@RequestMapping("/recommend")
public class RecommendController {

    @Autowired
    private RecommendService recommendService;

    @ResponseBody
    @RequestMapping(value = "/page", method = RequestMethod.GET)
    public Result<PageResult<BizRecommendRecord>> page(
            @RequestParam(required = false) Long customerId,
            @RequestParam(defaultValue = "1") int pageNum,
            @RequestParam(defaultValue = "10") int pageSize) {
        return Result.ok(recommendService.page(customerId, pageNum, pageSize));
    }
}
