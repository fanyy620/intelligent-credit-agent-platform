package com.credit.web.service;

import java.util.Map;

/** 认证服务 */
public interface AuthService {

    /** 登录：校验密码 → 签发 JWT → 写入 Redis（2h） */
    Map<String, Object> login(String username, String rawPassword);

    /** 注销：删除 Redis 令牌键 */
    void logout(String token);

    /** 当前登录用户信息（由拦截器写入 request attribute 的 JSON 解析） */
    Map<String, Object> parseUserJson(String userJson);
}
