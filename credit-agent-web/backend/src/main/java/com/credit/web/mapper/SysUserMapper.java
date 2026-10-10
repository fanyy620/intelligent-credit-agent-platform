package com.credit.web.mapper;

import java.util.List;

import org.apache.ibatis.annotations.Param;

import com.credit.web.entity.SysUser;

/** 系统用户 Mapper */
public interface SysUserMapper {

    SysUser selectByUsername(@Param("username") String username);

    SysUser selectById(@Param("id") Long id);

    List<SysUser> selectAll();
}
