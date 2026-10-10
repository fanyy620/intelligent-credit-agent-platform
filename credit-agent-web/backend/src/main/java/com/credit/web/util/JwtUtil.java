package com.credit.web.util;

import java.nio.charset.StandardCharsets;
import java.util.Date;
import java.util.UUID;

import javax.crypto.SecretKey;

import io.jsonwebtoken.Claims;
import io.jsonwebtoken.Jwts;
import io.jsonwebtoken.security.Keys;

/**
 * JWT 工具（jjwt 0.11.x，HS256）。
 *
 * 设计：JWT 内携带 username（subject）与 jti（令牌ID），
 * 同时把 jti → 用户信息 写入 Redis（2h 过期）。
 * 拦截器校验 = JWT 签名/有效期 + Redis 存在性双重确认，
 * 注销即删 Redis 键，实现可踢人、可吊销的有状态 JWT。
 */
public final class JwtUtil {

    private JwtUtil() {
    }

    /** 令牌载荷（解析结果） */
    public static class TokenPayload {
        private final String username;
        private final String jti;

        public TokenPayload(String username, String jti) {
            this.username = username;
            this.jti = jti;
        }

        public String getUsername() {
            return username;
        }

        public String getJti() {
            return jti;
        }
    }

    private static SecretKey key(String secret) {
        // jjwt 0.11.x：HS256 密钥需 >= 256bit，直接使用 UTF-8 字节
        return Keys.hmacShaKeyFor(secret.getBytes(StandardCharsets.UTF_8));
    }

    /** 签发令牌，返回 [jwt, jti] */
    public static String[] createToken(String secret, String username, long expireSeconds) {
        String jti = UUID.randomUUID().toString().replace("-", "");
        long now = System.currentTimeMillis();
        String jwt = Jwts.builder()
                .setSubject(username)
                .setId(jti)
                .setIssuedAt(new Date(now))
                .setExpiration(new Date(now + expireSeconds * 1000L))
                .signWith(key(secret))
                .compact();
        return new String[]{jwt, jti};
    }

    /** 解析并校验签名与有效期；非法时抛出异常 */
    public static TokenPayload parse(String secret, String jwt) {
        Claims claims = Jwts.parserBuilder()
                .setSigningKey(key(secret))
                .build()
                .parseClaimsJws(jwt)
                .getBody();
        return new TokenPayload(claims.getSubject(), claims.getId());
    }
}
