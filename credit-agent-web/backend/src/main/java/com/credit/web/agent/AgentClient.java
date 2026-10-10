package com.credit.web.agent;

import java.util.HashMap;
import java.util.List;
import java.util.Map;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.http.HttpEntity;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.stereotype.Component;
import org.springframework.web.client.RestTemplate;

/**
 * Python Agent 服务调用封装（RestTemplate + 超时 + 失败降级）。
 *
 * 降级纪律：Agent 服务（src/api_server.py）不可用时，所有方法返回
 * available=false 的兜底结构，绝不向上抛异常 —— 网站其他功能
 * （客户/产品/记录管理）不受影响。
 */
@Component
public class AgentClient {

    private static final Logger log = LoggerFactory.getLogger(AgentClient.class);

    @Autowired
    private RestTemplate restTemplate;

    @Value("${agent.base-url}")
    private String baseUrl;

    // ------------------------------------------------------------------ 基础设施

    private HttpEntity<Map<String, Object>> jsonEntity(Map<String, Object> body) {
        HttpHeaders headers = new HttpHeaders();
        headers.setContentType(MediaType.APPLICATION_JSON);
        return new HttpEntity<Map<String, Object>>(body, headers);
    }

    @SuppressWarnings("unchecked")
    private Map<String, Object> post(String path, Map<String, Object> body) {
        Map<String, Object> resp = restTemplate.postForObject(baseUrl + path, jsonEntity(body), Map.class);
        if (resp == null) {
            throw new IllegalStateException("Agent 返回空响应");
        }
        Object code = resp.get("code");
        if (code == null || ((Number) code).intValue() != 0) {
            throw new IllegalStateException("Agent 业务错误: " + resp.get("message"));
        }
        Object data = resp.get("data");
        if (data instanceof Map) {
            return (Map<String, Object>) data;
        }
        Map<String, Object> wrapper = new HashMap<String, Object>();
        wrapper.put("data", data);
        return wrapper;
    }

    private Map<String, Object> fallback(String what, Exception e) {
        log.warn("Agent 服务不可用（{}），已降级: {}", what, e.getMessage());
        Map<String, Object> map = new HashMap<String, Object>();
        map.put("available", false);
        map.put("reply", "智能助理暂时不可用，请稍后再试。您可先使用客户管理、产品管理等功能。");
        map.put("error", e.getClass().getSimpleName());
        return map;
    }

    // ------------------------------------------------------------------ 能力

    /** 健康探测 */
    public boolean health() {
        try {
            @SuppressWarnings("unchecked")
            Map<String, Object> resp = restTemplate.getForObject(baseUrl + "/health", Map.class);
            return resp != null && ((Number) resp.get("code")).intValue() == 0;
        } catch (Exception e) {
            return false;
        }
    }

    /** 对话：走完整 Agent 流水线 */
    public Map<String, Object> chat(String sessionId, String userId, String message) {
        Map<String, Object> body = new HashMap<String, Object>();
        body.put("session_id", sessionId);
        body.put("user_id", userId);
        body.put("message", message);
        try {
            Map<String, Object> data = post("/v1/chat", body);
            data.put("available", true);
            return data;
        } catch (Exception e) {
            return fallback("chat", e);
        }
    }

    /** 营销文案生成（模板填充 + 合规审核） */
    public Map<String, Object> generateCopy(String userId, String productId, String channel) {
        Map<String, Object> body = new HashMap<String, Object>();
        body.put("user_id", userId);
        body.put("product_id", productId);
        body.put("channel", channel);
        try {
            Map<String, Object> data = post("/v1/copy/generate", body);
            data.put("available", true);
            return data;
        } catch (Exception e) {
            return fallback("copy/generate", e);
        }
    }

    /** 合规审核 */
    @SuppressWarnings("unchecked")
    public Map<String, Object> complianceCheck(String text) {
        Map<String, Object> body = new HashMap<String, Object>();
        body.put("text", text);
        try {
            Map<String, Object> data = post("/v1/compliance/check", body);
            data.put("available", true);
            return data;
        } catch (Exception e) {
            return fallback("compliance/check", e);
        }
    }

    /** 产品库（Agent 侧） */
    @SuppressWarnings("unchecked")
    public List<Map<String, Object>> products() {
        try {
            Map<String, Object> resp = restTemplate.getForObject(baseUrl + "/v1/products", Map.class);
            if (resp != null && ((Number) resp.get("code")).intValue() == 0) {
                return (List<Map<String, Object>>) resp.get("data");
            }
        } catch (Exception e) {
            log.warn("Agent products 拉取失败（已降级）: {}", e.getMessage());
        }
        return java.util.Collections.emptyList();
    }
}
