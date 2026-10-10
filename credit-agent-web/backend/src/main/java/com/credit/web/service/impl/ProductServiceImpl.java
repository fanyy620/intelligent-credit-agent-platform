package com.credit.web.service.impl;

import java.util.List;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import com.credit.web.common.BusinessException;
import com.credit.web.entity.BizProduct;
import com.credit.web.mapper.BizProductMapper;
import com.credit.web.service.ProductService;
import com.credit.web.util.RedisUtil;
import com.fasterxml.jackson.core.type.TypeReference;
import com.fasterxml.jackson.databind.ObjectMapper;

/**
 * 信贷产品服务实现。
 * 列表读取走 Redis 缓存（web:product:list，10 分钟），
 * 增删改后清理缓存 —— 经典的“读多写少”缓存模式。
 */
@Service
public class ProductServiceImpl implements ProductService {

    private static final Logger log = LoggerFactory.getLogger(ProductServiceImpl.class);
    private static final String CACHE_KEY = "web:product:list";
    private static final int CACHE_SECONDS = 600;
    private static final ObjectMapper MAPPER = new ObjectMapper();

    @Autowired
    private BizProductMapper bizProductMapper;

    @Autowired
    private RedisUtil redisUtil;

    @Override
    public List<BizProduct> listOnSale() {
        // 1) 先查缓存
        try {
            String cached = redisUtil.get(CACHE_KEY);
            if (cached != null) {
                return MAPPER.readValue(cached, new TypeReference<List<BizProduct>>() {
                });
            }
        } catch (Exception e) {
            log.warn("产品缓存读取失败，回源数据库: {}", e.getMessage());
        }
        // 2) 回源并回填
        List<BizProduct> list = bizProductMapper.selectAllOnSale();
        try {
            redisUtil.set(CACHE_KEY, MAPPER.writeValueAsString(list), CACHE_SECONDS);
        } catch (Exception e) {
            log.warn("产品缓存回填失败（不影响读取）: {}", e.getMessage());
        }
        return list;
    }

    @Override
    @Transactional
    public BizProduct create(BizProduct product) {
        validate(product);
        if (product.getStatus() == null) {
            product.setStatus(1);
        }
        bizProductMapper.insert(product);
        evictCache();
        return product;
    }

    @Override
    @Transactional
    public int update(BizProduct product) {
        if (product.getId() == null) {
            throw new BusinessException("缺少产品ID");
        }
        int rows = bizProductMapper.updateById(product);
        if (rows == 0) {
            throw new BusinessException("产品不存在: id=" + product.getId());
        }
        evictCache();
        return rows;
    }

    @Override
    @Transactional
    public int delete(Long id) {
        int rows = bizProductMapper.deleteById(id);
        if (rows == 0) {
            throw new BusinessException("产品不存在: id=" + id);
        }
        evictCache();
        return rows;
    }

    private void validate(BizProduct p) {
        if (p.getProductCode() == null || p.getProductCode().trim().isEmpty()) {
            throw new BusinessException("产品编码不能为空");
        }
        if (p.getName() == null || p.getName().trim().isEmpty()) {
            throw new BusinessException("产品名称不能为空");
        }
        if (p.getMaxAmount() != null && p.getMinAmount() != null
                && p.getMaxAmount().compareTo(p.getMinAmount()) < 0) {
            throw new BusinessException("最高额度不能低于起借金额");
        }
    }

    private void evictCache() {
        redisUtil.delete(CACHE_KEY);
    }
}
