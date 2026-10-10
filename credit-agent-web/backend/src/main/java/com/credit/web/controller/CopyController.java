package com.credit.web.controller;

import java.util.Map;

import javax.servlet.http.HttpServletRequest;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.stereotype.Controller;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestMethod;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.ResponseBody;

import com.credit.web.common.PageResult;
import com.credit.web.common.Result;
import com.credit.web.dto.CopyGenerateRequest;
import com.credit.web.entity.BizCopyRecord;
import com.credit.web.service.CopyService;
import com.credit.web.util.LoginContext;

/** 营销文案与合规控制器 */
@Controller
@RequestMapping("/copy")
public class CopyController {

    @Autowired
    private CopyService copyService;

    /** 生成文案（模板填充 + 合规审核 + 落库） */
    @ResponseBody
    @RequestMapping(value = "/generate", method = RequestMethod.POST)
    public Result<Map<String, Object>> generate(@RequestBody CopyGenerateRequest body,
                                                HttpServletRequest request) {
        return Result.ok(copyService.generate(body, LoginContext.currentUserId(request)));
    }

    /** 记录分页（onlyViolation=true 时仅看违规） */
    @ResponseBody
    @RequestMapping(value = "/page", method = RequestMethod.GET)
    public Result<PageResult<BizCopyRecord>> page(
            @RequestParam(defaultValue = "false") boolean onlyViolation,
            @RequestParam(defaultValue = "1") int pageNum,
            @RequestParam(defaultValue = "10") int pageSize) {
        return Result.ok(copyService.page(onlyViolation, pageNum, pageSize));
    }
}
