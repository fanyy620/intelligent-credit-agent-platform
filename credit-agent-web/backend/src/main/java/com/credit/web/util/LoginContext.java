package com.credit.web.util;

import java.util.Map;

import javax.servlet.http.HttpServletRequest;

import com.credit.web.common.BusinessException;
import com.credit.web.common.Result;
import com.credit.web.interceptor.TokenInterceptor;
import com.fasterxml.jackson.databind.ObjectMapper;

/**
 * 登录上下文：从 request attribute（拦截器写入）解析当前登录用户。
 */
public final class LoginContext {

    private static final ObjectMapper MAPPER = new ObjectMapper();

    private LoginContext() {
    }

    @SuppressWarnings("unchecked")
    public static Map<String, Object> currentUser(HttpServletRequest request) {
        Object json = request.getAttribute(TokenInterceptor.ATTR_USER_JSON);
        if (json == null) {
            throw new BusinessException(Result.CODE_UNAUTHORIZED, "登录状态缺失");
        }
        try {
            return MAPPER.readValue((String) json, Map.class);
        } catch (Exception e) {
            throw new BusinessException(Result.CODE_UNAUTHORIZED, "登录状态解析失败");
        }
    }

    public static Long currentUserId(HttpServletRequest request) {
        Object id = currentUser(request).get("id");
        return id == null ? null : ((Number) id).longValue();
    }

    public static String currentUsername(HttpServletRequest request) {
        Object name = currentUser(request).get("username");
        return name == null ? "" : String.valueOf(name);
    }

    public static boolean isAdmin(HttpServletRequest request) {
        Object role = currentUser(request).get("roleKey");
        return "admin".equals(role);
    }

    /** 要求管理员权限，否则抛 403 */
    public static void requireAdmin(HttpServletRequest request) {
        if (!isAdmin(request)) {
            throw new BusinessException(Result.CODE_FORBIDDEN, "需要管理员权限");
        }
    }
}
