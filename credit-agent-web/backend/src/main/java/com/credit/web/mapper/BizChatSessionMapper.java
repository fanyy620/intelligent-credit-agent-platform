package com.credit.web.mapper;

import java.util.List;

import org.apache.ibatis.annotations.Param;

import com.credit.web.entity.BizChatSession;

/** 对话会话 Mapper */
public interface BizChatSessionMapper {

    int insert(BizChatSession session);

    BizChatSession selectById(@Param("id") Long id);

    BizChatSession selectBySessionNo(@Param("sessionNo") String sessionNo);

    List<BizChatSession> selectByUserId(@Param("userId") Long userId,
                                        @Param("offset") int offset,
                                        @Param("limit") int limit);

    int touchUpdateTime(@Param("id") Long id);
}
