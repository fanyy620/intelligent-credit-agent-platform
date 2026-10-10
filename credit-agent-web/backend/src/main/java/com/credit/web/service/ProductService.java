package com.credit.web.service;

import java.util.List;

import com.credit.web.entity.BizProduct;

/** 信贷产品服务（列表走 Redis 缓存，变更清缓存） */
public interface ProductService {

    List<BizProduct> listOnSale();

    BizProduct create(BizProduct product);

    int update(BizProduct product);

    int delete(Long id);
}
