package com.credit.web.controller;

import java.util.List;
import java.util.Map;

import javax.servlet.http.HttpServletRequest;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.stereotype.Controller;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestMethod;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.ResponseBody;

import com.credit.web.common.Result;
import com.credit.web.dto.ChatSendRequest;
import com.credit.web.entity.BizChatMessage;
import com.credit.web.entity.BizChatSession;
import com.credit.web.service.ChatService;
import com.credit.web.util.LoginContext;

/** 智能对话控制器：发消息 / 会话列表 / 历史消息 */
@Controller
@RequestMapping("/chat")
public class ChatController {

    @Autowired
    private ChatService chatService;

    /** 发送消息（核心端点：调用 Python Agent，降级时网站不受影响） */
    @ResponseBody
    @RequestMapping(value = "/send", method = RequestMethod.POST)
    public Result<Map<String, Object>> send(@RequestBody ChatSendRequest body,
                                            HttpServletRequest request) {
        Long userId = LoginContext.currentUserId(request);
        String username = LoginContext.currentUsername(request);
        return Result.ok(chatService.send(body, userId, username));
    }

    /** 当前用户的会话列表（最近活跃在前） */
    @ResponseBody
    @RequestMapping(value = "/sessions", method = RequestMethod.GET)
    public Result<List<BizChatSession>> sessions(@RequestParam(defaultValue = "50") int limit,
                                                 HttpServletRequest request) {
        return Result.ok(chatService.listSessions(LoginContext.currentUserId(request), limit));
    }

    /** 会话历史消息 */
    @ResponseBody
    @RequestMapping(value = "/messages", method = RequestMethod.GET)
    public Result<List<BizChatMessage>> messages(@RequestParam Long sessionId,
                                                 HttpServletRequest request) {
        return Result.ok(chatService.listMessages(sessionId, LoginContext.currentUserId(request)));
    }
}
