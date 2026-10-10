package com.credit.web.service.impl;

import java.util.List;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.stereotype.Service;

import com.credit.web.entity.SysRole;
import com.credit.web.entity.SysUser;
import com.credit.web.mapper.SysRoleMapper;
import com.credit.web.mapper.SysUserMapper;
import com.credit.web.service.UserService;

/** 用户与角色服务实现 */
@Service
public class UserServiceImpl implements UserService {

    @Autowired
    private SysUserMapper sysUserMapper;

    @Autowired
    private SysRoleMapper sysRoleMapper;

    @Override
    public List<SysUser> listUsers() {
        List<SysUser> users = sysUserMapper.selectAll();
        // 用户列表不回传密码哈希与盐值
        for (SysUser u : users) {
            u.setPassword(null);
            u.setSalt(null);
        }
        return users;
    }

    @Override
    public List<SysRole> listRoles() {
        return sysRoleMapper.selectAll();
    }
}
