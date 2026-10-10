package com.credit.web.controller;

import java.util.HashMap;
import java.util.Map;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.stereotype.Controller;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestMethod;
import org.springframework.web.bind.annotation.ResponseBody;

import com.credit.web.agent.AgentClient;
import com.credit.web.common.Result;
import com.credit.web.service.DashboardService;

/** 数据看板 + 健康检查控制器 */
@Controller
public class DashboardController {

    @Autowired
    private DashboardService dashboardService;

    @Autowired
    private AgentClient agentClient;

    /** 首页聚合统计 */
    @ResponseBody
    @RequestMapping(value = "/dashboard/stats", method = RequestMethod.GET)
    public Result<Map<String, Object>> stats() {
        return Result.ok(dashboardService.stats());
    }

    /** 健康检查（拦截器放行）：网站与 Agent 双状态 */
    @ResponseBody
    @RequestMapping(value = "/health", method = RequestMethod.GET)
    public Result<Map<String, Object>> health() {
        Map<String, Object> data = new HashMap<String, Object>();
        data.put("web", "up");
        data.put("agent", agentClient.health() ? "up" : "down");
        return Result.ok(data);
    }
}
