package com.credit.web.util;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import redis.clients.jedis.Jedis;
import redis.clients.jedis.JedisPool;

/**
 * Redis 操作工具（Jedis 封装）。
 *
 * Redis 不可用时所有操作静默降级（返回 null/false），
 * 由调用方决定兜底策略 —— 保证“Redis 挂了网站仍可读库运行”，
 * 仅登录态、缓存、会话上下文等功能退化。
 */
public class RedisUtil {

    private static final Logger log = LoggerFactory.getLogger(RedisUtil.class);

    private JedisPool jedisPool;

    public void setJedisPool(JedisPool jedisPool) {
        this.jedisPool = jedisPool;
    }

    public void set(String key, String value, int expireSeconds) {
        try (Jedis jedis = jedisPool.getResource()) {
            if (expireSeconds > 0) {
                jedis.setex(key, expireSeconds, value);
            } else {
                jedis.set(key, value);
            }
        } catch (Exception e) {
            log.warn("Redis 写入失败（已降级）: key={}, err={}", key, e.getMessage());
        }
    }

    public String get(String key) {
        try (Jedis jedis = jedisPool.getResource()) {
            return jedis.get(key);
        } catch (Exception e) {
            log.warn("Redis 读取失败（已降级）: key={}, err={}", key, e.getMessage());
            return null;
        }
    }

    public void delete(String key) {
        try (Jedis jedis = jedisPool.getResource()) {
            jedis.del(key);
        } catch (Exception e) {
            log.warn("Redis 删除失败（已降级）: key={}, err={}", key, e.getMessage());
        }
    }

    /** 键存在性（用于令牌有效性校验）；Redis 故障时返回 false → 视为未登录 */
    public boolean exists(String key) {
        try (Jedis jedis = jedisPool.getResource()) {
            return jedis.exists(key);
        } catch (Exception e) {
            log.warn("Redis exists 失败（已降级）: key={}, err={}", key, e.getMessage());
            return false;
        }
    }
}
