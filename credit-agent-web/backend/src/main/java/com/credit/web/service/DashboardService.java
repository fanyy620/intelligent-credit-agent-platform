package com.credit.web.service;

import java.util.Map;

/** 数据看板服务 */
public interface DashboardService {

    /** 首页聚合：今日对话/今日推荐/合规通过率/意图分布/总量卡片/Agent 健康 */
    Map<String, Object> stats();
}
