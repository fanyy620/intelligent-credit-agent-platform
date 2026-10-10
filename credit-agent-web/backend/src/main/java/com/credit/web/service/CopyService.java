package com.credit.web.service;

import java.util.Map;

import com.credit.web.common.PageResult;
import com.credit.web.dto.CopyGenerateRequest;
import com.credit.web.entity.BizCopyRecord;

/** 营销文案与合规服务 */
public interface CopyService {

    /** 生成文案：调 Agent 模板填充 → 合规审核 → 落库 */
    Map<String, Object> generate(CopyGenerateRequest request, Long userId);

    PageResult<BizCopyRecord> page(boolean onlyViolation, int pageNum, int pageSize);
}
