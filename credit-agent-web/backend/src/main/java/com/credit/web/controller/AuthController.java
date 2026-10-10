package com.credit.web.controller;

import java.util.Map;

import javax.servlet.http.HttpServletRequest;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.stereotype.Controller;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestMethod;
import org.springframework.web.bind.annotation.ResponseBody;

import com.credit.web.common.Result;
import com.credit.web.dto.LoginRequest;
import com.credit.web.service.AuthService;
import com.credit.web.util.LoginContext;

/** 认证控制器：登录 / 注销 / 当前用户 */
@Controller
@RequestMapping("/auth")
public class AuthController {

    @Autowired
    private AuthService authService;

    /** 登录（拦截器放行路径） */
    @ResponseBody
    @RequestMapping(value = "/login", method = RequestMethod.POST)
    public Result<Map<String, Object>> login(@RequestBody LoginRequest request) {
        return Result.ok("登录成功", authService.login(request.getUsername(), request.getPassword()));
    }

    /** 注销 */
    @ResponseBody
    @RequestMapping(value = "/logout", method = RequestMethod.POST)
    public Result<Void> logout(HttpServletRequest request) {
        String token = request.getHeader("Authorization");
        if (token != null && token.startsWith("Bearer ")) {
            token = token.substring(7).trim();
        } else {
            token = request.getHeader("token");
        }
        authService.logout(token);
        return Result.ok("已注销", null);
    }

    /** 当前登录用户信息 */
    @ResponseBody
    @RequestMapping(value = "/info", method = RequestMethod.GET)
    public Result<Map<String, Object>> info(HttpServletRequest request) {
        return Result.ok(LoginContext.currentUser(request));
    }
}
