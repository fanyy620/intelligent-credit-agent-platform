package com.credit.web.entity;

import java.io.Serializable;

/** 系统角色（sys_role） */
public class SysRole implements Serializable {

    private static final long serialVersionUID = 1L;

    private Long id;
    private String roleKey;
    private String roleName;
    private String remark;

    public Long getId() { return id; }
    public void setId(Long id) { this.id = id; }
    public String getRoleKey() { return roleKey; }
    public void setRoleKey(String roleKey) { this.roleKey = roleKey; }
    public String getRoleName() { return roleName; }
    public void setRoleName(String roleName) { this.roleName = roleName; }
    public String getRemark() { return remark; }
    public void setRemark(String remark) { this.remark = remark; }
}
