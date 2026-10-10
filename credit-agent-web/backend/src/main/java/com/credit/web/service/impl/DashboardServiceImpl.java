package com.credit.web.service.impl;

import java.util.HashMap;
import java.util.List;
import java.util.Map;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.stereotype.Service;

import com.credit.web.agent.AgentClient;
import com.credit.web.mapper.DashboardMapper;
import com.credit.web.service.DashboardService;

/** 数据看板服务实现：SQL 聚合 + Agent 健康探测 */
@Service
public class DashboardServiceImpl implements DashboardService {

    @Autowired
    private DashboardMapper dashboardMapper;

    @Autowired
    private AgentClient agentClient;

    @Override
    @SuppressWarnings("unchecked")
    public Map<String, Object> stats() {
        Map<String, Object> result = new HashMap<String, Object>();

        result.put("todayChatCount", dashboardMapper.selectTodayChatCount());
        result.put("todayRecommendCount", dashboardMapper.selectTodayRecommendCount());
        result.put("customerCount", dashboardMapper.selectCustomerCount());
        result.put("sessionCount", dashboardMapper.selectSessionCount());

        // 合规通过率（无文案记录时视为 100%）
        Map<String, Object> summary = dashboardMapper.selectComplianceSummary();
        long total = summary == null ? 0L : ((Number) summary.get("total")).longValue();
        long passed = summary == null ? 0L : ((Number) summary.get("passed")).longValue();
        Map<String, Object> compliance = new HashMap<String, Object>();
        compliance.put("total", total);
        compliance.put("passed", passed);
        compliance.put("passRate", total == 0 ? 1.0 : (double) passed / (double) total);
        result.put("compliance", compliance);

        // 意图分布（intent/intent_zh/cnt）
        List<Map<String, Object>> distribution = dashboardMapper.selectIntentDistribution();
        result.put("intentDistribution", distribution);

        // Agent 服务健康状态（前端卡片提示用）
        result.put("agentAvailable", agentClient.health());
        return result;
    }
}
