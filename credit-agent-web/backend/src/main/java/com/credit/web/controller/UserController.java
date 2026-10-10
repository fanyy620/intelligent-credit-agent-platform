package com.credit.web.controller;

import java.util.List;

import javax.servlet.http.HttpServletRequest;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.stereotype.Controller;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestMethod;
import org.springframework.web.bind.annotation.ResponseBody;

import com.credit.web.common.Result;
import com.credit.web.entity.SysRole;
import com.credit.web.entity.SysUser;
import com.credit.web.service.UserService;
import com.credit.web.util.LoginContext;

/** 用户与角色控制器（用户列表仅管理员可见） */
@Controller
@RequestMapping("/system")
public class UserController {

    @Autowired
    private UserService userService;

    @ResponseBody
    @RequestMapping(value = "/user/list", method = RequestMethod.GET)
    public Result<List<SysUser>> listUsers(HttpServletRequest request) {
        LoginContext.requireAdmin(request);
        return Result.ok(userService.listUsers());
    }

    @ResponseBody
    @RequestMapping(value = "/role/list", method = RequestMethod.GET)
    public Result<List<SysRole>> listRoles() {
        return Result.ok(userService.listRoles());
    }
}
