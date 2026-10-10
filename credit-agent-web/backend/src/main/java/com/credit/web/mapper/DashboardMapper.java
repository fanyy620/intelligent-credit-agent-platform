package com.credit.web.mapper;

import java.util.List;
import java.util.Map;

/** 数据看板聚合查询 Mapper（纯 SQL 聚合，无实体表） */
public interface DashboardMapper {

    /** 今日对话轮数（用户消息条数） */
    long selectTodayChatCount();

    /** 今日推荐次数 */
    long selectTodayRecommendCount();

    /** 合规统计：total / passed */
    Map<String, Object> selectComplianceSummary();

    /** 意图分布：intent / intent_zh / cnt */
    List<Map<String, Object>> selectIntentDistribution();

    /** 客户总数 */
    long selectCustomerCount();

    /** 会话总数 */
    long selectSessionCount();
}
