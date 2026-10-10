package com.credit.web.service.impl;

import java.util.HashMap;
import java.util.Map;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Service;

import com.credit.web.common.BusinessException;
import com.credit.web.common.Result;
import com.credit.web.entity.SysUser;
import com.credit.web.mapper.SysUserMapper;
import com.credit.web.service.AuthService;
import com.credit.web.util.JwtUtil;
import com.credit.web.util.PasswordUtil;
import com.credit.web.util.RedisUtil;
import com.fasterxml.jackson.databind.ObjectMapper;

/**
 * 认证服务实现：MD5盐值校验 → jjwt 签发 → Redis 存登录态（2h）。
 * Redis 键：web:token:{jti} → 用户信息 JSON。
 */
@Service
public class AuthServiceImpl implements AuthService {

    private static final ObjectMapper MAPPER = new ObjectMapper();

    @Autowired
    private SysUserMapper sysUserMapper;

    @Autowired
    private RedisUtil redisUtil;

    @Value("${jwt.secret}")
    private String jwtSecret;

    @Value("${jwt.expire-seconds}")
    private long expireSeconds;

    @Override
    public Map<String, Object> login(String username, String rawPassword) {
        if (username == null || username.trim().isEmpty()
                || rawPassword == null || rawPassword.isEmpty()) {
            throw new BusinessException("账号和密码不能为空");
        }
        SysUser user = sysUserMapper.selectByUsername(username.trim());
        if (user == null) {
            throw new BusinessException("账号不存在");
        }
        if (user.getStatus() == null || user.getStatus() != 1) {
            throw new BusinessException("账号已被停用，请联系管理员");
        }
        if (!PasswordUtil.verify(user.getSalt(), rawPassword, user.getPassword())) {
            throw new BusinessException("密码错误");
        }

        // 签发 JWT（jti 作为 Redis 登录态键）
        String[] pair = JwtUtil.createToken(jwtSecret, user.getUsername(), expireSeconds);

        Map<String, Object> userInfo = new HashMap<String, Object>();
        userInfo.put("id", user.getId());
        userInfo.put("username", user.getUsername());
        userInfo.put("nickname", user.getNickname());
        userInfo.put("roleKey", user.getRoleKey());
        userInfo.put("roleName", user.getRoleName());
        try {
            redisUtil.set("web:token:" + pair[1], MAPPER.writeValueAsString(userInfo),
                    (int) expireSeconds);
        } catch (Exception e) {
            throw new IllegalStateException("用户信息序列化失败", e);
        }

        Map<String, Object> result = new HashMap<String, Object>();
        result.put("token", pair[0]);
        result.put("user", userInfo);
        return result;
    }

    @Override
    public void logout(String token) {
        try {
            JwtUtil.TokenPayload payload = JwtUtil.parse(jwtSecret, token);
            redisUtil.delete("web:token:" + payload.getJti());
        } catch (Exception e) {
            // 令牌本身已无效，视为已注销，静默成功
        }
    }

    @Override
    @SuppressWarnings("unchecked")
    public Map<String, Object> parseUserJson(String userJson) {
        if (userJson == null) {
            throw new BusinessException(Result.CODE_UNAUTHORIZED, "登录状态缺失");
        }
        try {
            return MAPPER.readValue(userJson, Map.class);
        } catch (Exception e) {
            throw new BusinessException(Result.CODE_UNAUTHORIZED, "登录状态解析失败");
        }
    }
}
