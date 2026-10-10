package com.credit.web.service;

import java.util.List;

import com.credit.web.entity.SysRole;
import com.credit.web.entity.SysUser;

/** 用户与角色服务 */
public interface UserService {

    List<SysUser> listUsers();

    List<SysRole> listRoles();
}
