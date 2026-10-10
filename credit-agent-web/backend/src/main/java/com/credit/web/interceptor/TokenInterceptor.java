package com.credit.web.interceptor;

import java.io.IOException;
import java.io.PrintWriter;

import javax.servlet.http.HttpServletRequest;
import javax.servlet.http.HttpServletResponse;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.web.servlet.HandlerInterceptor;

import com.credit.web.util.JwtUtil;
import com.credit.web.util.RedisUtil;

/**
 * 登录令牌拦截器（XML 声明于 spring-mvc.xml）。
 *
 * 校验链：取 token（Authorization: Bearer 或 token 头）
 *   → JWT 签名/有效期（jjwt）
 *   → Redis 键 web:token:{jti} 存在性（支持注销/踢人）
 *   → 放行，并把 username / 用户JSON 写入 request attribute 供控制器使用。
 */
public class TokenInterceptor implements HandlerInterceptor {

    private static final Logger log = LoggerFactory.getLogger(TokenInterceptor.class);

    /** 注入到 request attribute 的键名 */
    public static final String ATTR_USERNAME = "loginUsername";
    public static final String ATTR_USER_JSON = "loginUserJson";

    private String jwtSecret;
    private RedisUtil redisUtil;

    public void setJwtSecret(String jwtSecret) {
        this.jwtSecret = jwtSecret;
    }

    public void setRedisUtil(RedisUtil redisUtil) {
        this.redisUtil = redisUtil;
    }

    @Override
    public boolean preHandle(HttpServletRequest request, HttpServletResponse response, Object handler)
            throws Exception {
        // 预检请求直接放行（CorsFilter 已处理响应头）
        if ("OPTIONS".equalsIgnoreCase(request.getMethod())) {
            return true;
        }

        String token = resolveToken(request);
        if (token == null) {
            writeUnauthorized(response, "未登录或缺少令牌");
            return false;
        }

        final JwtUtil.TokenPayload payload;
        try {
            payload = JwtUtil.parse(jwtSecret, token);
        } catch (Exception e) {
            log.debug("JWT 校验失败: {}", e.getMessage());
            writeUnauthorized(response, "令牌无效或已过期，请重新登录");
            return false;
        }

        String userJson = redisUtil.get("web:token:" + payload.getJti());
        if (userJson == null) {
            writeUnauthorized(response, "登录状态已失效（可能已注销），请重新登录");
            return false;
        }

        request.setAttribute(ATTR_USERNAME, payload.getUsername());
        request.setAttribute(ATTR_USER_JSON, userJson);
        return true;
    }

    private String resolveToken(HttpServletRequest request) {
        String auth = request.getHeader("Authorization");
        if (auth != null && auth.startsWith("Bearer ")) {
            return auth.substring(7).trim();
        }
        String token = request.getHeader("token");
        return (token == null || token.isEmpty()) ? null : token;
    }

    private void writeUnauthorized(HttpServletResponse response, String message) throws IOException {
        response.setStatus(HttpServletResponse.SC_OK); // 统一 200 + code=401，由前端拦截器处理
        response.setContentType("application/json;charset=UTF-8");
        PrintWriter writer = response.getWriter();
        writer.write("{\"code\":401,\"message\":\"" + message + "\",\"data\":null}");
        writer.flush();
    }
}
