package com.credit.web.mapper;

import java.util.List;

import org.apache.ibatis.annotations.Param;

import com.credit.web.entity.BizChatMessage;

/** 对话消息 Mapper */
public interface BizChatMessageMapper {

    int insert(BizChatMessage message);

    List<BizChatMessage> selectBySessionId(@Param("sessionId") Long sessionId);
}
