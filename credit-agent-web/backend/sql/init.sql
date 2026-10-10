-- ====================================================================
-- credit-agent-web 初始化脚本（MySQL 8）
-- 用法：mysql -uroot -p < sql/init.sql
-- 内容：建库、建表、RBAC 种子账号、示例客户、8 个信贷产品（与
--       credit-agent-platform/configs/products.yaml 字段对齐）
-- ====================================================================

CREATE DATABASE IF NOT EXISTS credit_web
    DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci;
USE credit_web;

-- ---------------------------------------------------------------- 角色
DROP TABLE IF EXISTS sys_role;
CREATE TABLE sys_role (
    id          BIGINT      NOT NULL AUTO_INCREMENT COMMENT '主键',
    role_key    VARCHAR(32) NOT NULL COMMENT '角色标识（admin/manager）',
    role_name   VARCHAR(64) NOT NULL COMMENT '角色名称',
    remark      VARCHAR(255) DEFAULT '' COMMENT '备注',
    PRIMARY KEY (id),
    UNIQUE KEY uk_role_key (role_key)
) ENGINE = InnoDB COMMENT '系统角色表';

-- ---------------------------------------------------------------- 用户
DROP TABLE IF EXISTS sys_user;
CREATE TABLE sys_user (
    id          BIGINT      NOT NULL AUTO_INCREMENT COMMENT '主键',
    username    VARCHAR(32) NOT NULL COMMENT '登录账号',
    password    VARCHAR(64) NOT NULL COMMENT '密码哈希（MD5(盐+明文)）',
    salt        VARCHAR(16) NOT NULL COMMENT '盐值',
    nickname    VARCHAR(64) NOT NULL DEFAULT '' COMMENT '姓名/昵称',
    role_id     BIGINT      NOT NULL COMMENT '角色ID',
    status      TINYINT     NOT NULL DEFAULT 1 COMMENT '状态 1正常 0停用',
    create_time DATETIME    NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    PRIMARY KEY (id),
    UNIQUE KEY uk_username (username),
    KEY idx_role (role_id)
) ENGINE = InnoDB COMMENT '系统用户表';

-- ---------------------------------------------------------------- 客户
DROP TABLE IF EXISTS biz_customer;
CREATE TABLE biz_customer (
    id             BIGINT       NOT NULL AUTO_INCREMENT COMMENT '主键',
    name           VARCHAR(32)  NOT NULL COMMENT '客户姓名',
    gender         VARCHAR(4)   NOT NULL DEFAULT '男' COMMENT '性别',
    phone          VARCHAR(20)  NOT NULL DEFAULT '' COMMENT '手机号',
    age            INT          DEFAULT NULL COMMENT '年龄',
    occupation     VARCHAR(32)  NOT NULL DEFAULT '' COMMENT '职业身份（上班族/个体户/企业主/学生…）',
    monthly_income DECIMAL(12,2) DEFAULT NULL COMMENT '月收入（元）',
    credit_status  VARCHAR(16)  NOT NULL DEFAULT '' COMMENT '征信情况（良好/一般/有逾期）',
    remark         VARCHAR(500) NOT NULL DEFAULT '' COMMENT '备注',
    create_by      VARCHAR(32)  NOT NULL DEFAULT '' COMMENT '归属客户经理',
    create_time    DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    update_time    DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
    PRIMARY KEY (id),
    KEY idx_name (name),
    KEY idx_phone (phone)
) ENGINE = InnoDB COMMENT '信贷客户表';

-- ---------------------------------------------------------------- 信贷产品
DROP TABLE IF EXISTS biz_product;
CREATE TABLE biz_product (
    id                 BIGINT       NOT NULL AUTO_INCREMENT COMMENT '主键',
    product_code       VARCHAR(32)  NOT NULL COMMENT '产品编码（与 Agent 产品库 id 对齐）',
    name               VARCHAR(32)  NOT NULL COMMENT '产品名称',
    category           VARCHAR(16)  NOT NULL COMMENT '产品类别（消费贷/经营贷/房抵贷/车贷）',
    min_amount         DECIMAL(14,2) NOT NULL COMMENT '起借金额（元）',
    max_amount         DECIMAL(14,2) NOT NULL COMMENT '最高额度（元）',
    min_term_months    INT          NOT NULL COMMENT '最短期限（月）',
    max_term_months    INT          NOT NULL COMMENT '最长期限（月）',
    annual_rate_min    DECIMAL(6,4) NOT NULL COMMENT '最低年化利率（小数）',
    annual_rate_max    DECIMAL(6,4) NOT NULL COMMENT '最高年化利率（小数）',
    approval_hours     DECIMAL(8,1) NOT NULL COMMENT '审批时效（小时）',
    min_age            INT          NOT NULL DEFAULT 18 COMMENT '最小年龄',
    max_age            INT          NOT NULL DEFAULT 65 COMMENT '最大年龄',
    min_monthly_income DECIMAL(12,2) NOT NULL DEFAULT 0 COMMENT '最低月收入（元）',
    min_credit_score   INT          NOT NULL DEFAULT 0 COMMENT '最低征信分',
    allowed_purposes   VARCHAR(255) NOT NULL DEFAULT '' COMMENT '准入用途（逗号分隔）',
    tags               VARCHAR(255) NOT NULL DEFAULT '' COMMENT '标签（逗号分隔）',
    description        VARCHAR(500) NOT NULL DEFAULT '' COMMENT '产品描述',
    status             TINYINT      NOT NULL DEFAULT 1 COMMENT '状态 1在售 0下架',
    create_time        DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    update_time        DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
    PRIMARY KEY (id),
    UNIQUE KEY uk_product_code (product_code),
    KEY idx_category (category)
) ENGINE = InnoDB COMMENT '信贷产品表';

-- ---------------------------------------------------------------- 对话会话
DROP TABLE IF EXISTS biz_chat_session;
CREATE TABLE biz_chat_session (
    id          BIGINT      NOT NULL AUTO_INCREMENT COMMENT '主键',
    session_no  VARCHAR(64) NOT NULL COMMENT '会话编号（与 Agent 侧 session_id 一致）',
    user_id     BIGINT      NOT NULL COMMENT '操作的客户经理ID',
    customer_id BIGINT      DEFAULT NULL COMMENT '关联客户ID',
    title       VARCHAR(64) NOT NULL DEFAULT '' COMMENT '会话标题（首条消息截取）',
    create_time DATETIME    NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    update_time DATETIME    NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '最近活跃时间',
    PRIMARY KEY (id),
    UNIQUE KEY uk_session_no (session_no),
    KEY idx_user (user_id),
    KEY idx_customer (customer_id)
) ENGINE = InnoDB COMMENT '智能助理对话会话表';

-- ---------------------------------------------------------------- 对话消息
DROP TABLE IF EXISTS biz_chat_message;
CREATE TABLE biz_chat_message (
    id          BIGINT      NOT NULL AUTO_INCREMENT COMMENT '主键',
    session_id  BIGINT      NOT NULL COMMENT '会话ID',
    role        VARCHAR(16) NOT NULL COMMENT '角色（user/assistant）',
    content     TEXT        NOT NULL COMMENT '消息内容',
    intent      VARCHAR(32) NOT NULL DEFAULT '' COMMENT '意图编码（assistant 消息）',
    intent_zh   VARCHAR(32) NOT NULL DEFAULT '' COMMENT '意图中文名',
    create_time DATETIME    NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    PRIMARY KEY (id),
    KEY idx_session (session_id),
    KEY idx_create_time (create_time),
    KEY idx_intent (intent)
) ENGINE = InnoDB COMMENT '对话消息表';

-- ---------------------------------------------------------------- 推荐记录
DROP TABLE IF EXISTS biz_recommend_record;
CREATE TABLE biz_recommend_record (
    id           BIGINT      NOT NULL AUTO_INCREMENT COMMENT '主键',
    session_id   BIGINT      NOT NULL COMMENT '会话ID',
    customer_id  BIGINT      DEFAULT NULL COMMENT '关联客户ID',
    user_id      BIGINT      NOT NULL COMMENT '操作的客户经理ID',
    message      TEXT        NOT NULL COMMENT '客户原始诉求',
    top_product  VARCHAR(32) NOT NULL DEFAULT '' COMMENT '综合分第一名产品',
    result_json  TEXT        NOT NULL COMMENT '推荐结果JSON（含四维评分明细）',
    create_time  DATETIME    NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    PRIMARY KEY (id),
    KEY idx_customer (customer_id),
    KEY idx_create_time (create_time)
) ENGINE = InnoDB COMMENT '授信推荐记录表';

-- ---------------------------------------------------------------- 文案与合规
DROP TABLE IF EXISTS biz_copy_record;
CREATE TABLE biz_copy_record (
    id           BIGINT      NOT NULL AUTO_INCREMENT COMMENT '主键',
    user_id      BIGINT      NOT NULL COMMENT '操作的客户经理ID',
    customer_id  BIGINT      DEFAULT NULL COMMENT '关联客户ID',
    product_id   VARCHAR(32) NOT NULL COMMENT '产品编码',
    product_name VARCHAR(32) NOT NULL COMMENT '产品名称',
    channel      VARCHAR(16) NOT NULL DEFAULT '朋友圈' COMMENT '投放渠道（朋友圈/短信/海报）',
    template     TEXT        COMMENT 'LLM 生成的模板（数值为槽位）',
    content      TEXT        NOT NULL COMMENT '最终文案（数值由结构化数据填充）',
    compliant    TINYINT     NOT NULL DEFAULT 1 COMMENT '合规结论 1通过 0违规',
    hit_rules    VARCHAR(500) NOT NULL DEFAULT '' COMMENT '命中规则明细（JSON数组）',
    conclusion   VARCHAR(255) NOT NULL DEFAULT '' COMMENT '审核结论说明',
    create_time  DATETIME    NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    PRIMARY KEY (id),
    KEY idx_user (user_id),
    KEY idx_compliant (compliant),
    KEY idx_create_time (create_time)
) ENGINE = InnoDB COMMENT '营销文案与合规审核记录表';

-- ====================================================================
-- 种子数据
-- ====================================================================

-- 角色
INSERT INTO sys_role (id, role_key, role_name, remark) VALUES
(1, 'admin',   '系统管理员', '全部功能权限'),
(2, 'manager', '客户经理',   '客户管理/智能助理/营销文案');

-- 用户（密码均为 123456，存储为 MD5(盐+明文)，盐值见 salt 列）
INSERT INTO sys_user (id, username, password, salt, nickname, role_id, status) VALUES
(1, 'admin',    '5e0ab52f58cad58a4bf59569bfca4e70', 'a1b2c3', '系统管理员', 1, 1),
(2, 'manager01','19bf45eaed94d788c75d2bdc26aba7fc', 'd4e5f6', '王客户经理', 2, 1);

-- 示例客户（对公演示：gender 复用为企业性质，age 为成立年限，
--   occupation 为所属行业，monthly_income 为月均营收）
INSERT INTO biz_customer (name, gender, phone, age, occupation, monthly_income, credit_status, remark, create_by) VALUES
('华创精密制造有限公司',   '民企', '0755-26881001', 12, '制造业',   8000000.00,  '良好',   '主营精密零部件，有200万流动资金贷款需求', 'manager01'),
('恒信贸易(深圳)有限公司', '民企', '0755-83232002', 8,  '贸易物流', 5000000.00,  '良好',   '进出口贸易，旺季备货融资需求', 'manager01'),
('南天物流集团有限公司',   '国企', '020-38990003',  15, '贸易物流', 20000000.00, '良好',   '区域物流龙头，车队扩张融资', 'manager01'),
('启明生物科技有限公司',   '民企', '0755-26504004', 5,  '医药科技', 3000000.00,  '良好',   '高新技术企业，研发投入占比高', 'manager01'),
('宏基建筑工程有限公司',   '民企', '0755-28995005', 20, '建筑工程', 15000000.00, '一般',   '项目垫资压力较大，关注供应链融资', 'admin'),
('悦达餐饮管理有限公司',   '小微', '0755-26666006', 4,  '餐饮服务', 900000.00,   '有逾期', '连锁门店，两年前有贷款逾期记录', 'manager01');

-- 信贷产品（与 credit-agent-platform/configs/products.yaml 同步）
INSERT INTO biz_product (product_code, name, category, min_amount, max_amount,
    min_term_months, max_term_months, annual_rate_min, annual_rate_max, approval_hours,
    min_age, max_age, min_monthly_income, min_credit_score, allowed_purposes, tags, description, status) VALUES
('xinxiangdai',     '信享贷',     '消费贷', 10000,  300000,  6,  36,  0.0480, 0.0960, 2,   22, 55, 4000, 600, '消费,装修,教育,旅游,医疗', '纯信用,线上申请,白领,免抵押', '面向优质工薪白领的纯信用消费贷款，线上申请免抵押，适合装修教育旅游医疗等大额消费场景', 1),
('xinyidai',        '薪易贷',     '消费贷', 5000,   200000,  3,  24,  0.0540, 0.1080, 1,   20, 50, 3000, 550, '消费,旅游,教育,医疗,周转', '工薪,代发工资,快速到账', '面向代发工资客群的短期小额消费信贷，凭打卡工资即可申请，最快一小时放款', 1),
('jisuxinyongdai',  '极速信用贷', '消费贷', 1000,   50000,   3,  12,  0.0720, 0.1440, 0.5, 20, 55, 2000, 520, '消费,周转', '小额,极速,纯线上,门槛最低', '小额短期应急信用贷款，全线上自动审批最快三十分钟出结果，门槛低但利率偏高', 1),
('xuezizhuxuedai',  '学子助学贷', '消费贷', 5000,   80000,   12, 60,  0.0360, 0.0490, 24,  18, 30, 0,    500, '教育,留学', '学生,教育分期,低息', '面向在校学生及留学群体的低息教育专项贷款，支持学费分期与生活费补助', 1),
('xingyejingyingdai','兴业经营贷','经营贷', 50000,  1000000, 6,  60,  0.0435, 0.0850, 24,  22, 60, 0,    550, '经营,周转,进货', '个体户,小微企业主,营业执照,流水', '面向个体工商户与小微企业主的经营性贷款，凭营业执照与经营流水申请，用于进货与资金周转', 1),
('shuiyidai',       '税易贷',     '经营贷', 100000, 3000000, 6,  36,  0.0385, 0.0650, 48,  23, 60, 0,    600, '经营,周转', '纳税记录,小微,纯信用,对公', '依据企业纳税信用记录授信的小微企业纯信用经营贷，纳税等级越高利率越低', 1),
('anjufangdidai',   '安居房抵贷', '房抵贷', 200000, 5000000, 12, 120, 0.0365, 0.0580, 72,  25, 60, 8000, 580, '经营,装修,消费', '房产抵押,大额,长期,低利率', '以住宅房产抵押的大额长期贷款，额度高利率低，适合大额装修经营投入等场景，审批需三到五个工作日', 1),
('cheyidai',        '车易贷',     '车贷',   30000,  500000,  12, 60,  0.0450, 0.0790, 4,   21, 55, 5000, 560, '购车,买车', '新车,二手车,按揭,经销商合作', '面向个人购车场景的汽车按揭贷款，支持新车与二手车，合作经销商可现场办理当天提车', 1);
