package com.credit.web.common;

import java.io.Serializable;

/**
 * 统一响应体：{code, message, data}
 * code=0 成功；400 参数错误；401 未登录/令牌失效；403 无权限；500 服务异常。
 * 与 Python Agent 服务的响应约定保持一致，前端 axios 拦截器统一处理。
 */
public class Result<T> implements Serializable {

    private static final long serialVersionUID = 1L;

    public static final int CODE_SUCCESS = 0;
    public static final int CODE_BAD_REQUEST = 400;
    public static final int CODE_UNAUTHORIZED = 401;
    public static final int CODE_FORBIDDEN = 403;
    public static final int CODE_ERROR = 500;

    private int code;
    private String message;
    private T data;

    public Result() {
    }

    public Result(int code, String message, T data) {
        this.code = code;
        this.message = message;
        this.data = data;
    }

    public static <T> Result<T> ok(T data) {
        return new Result<T>(CODE_SUCCESS, "ok", data);
    }

    public static <T> Result<T> ok(String message, T data) {
        return new Result<T>(CODE_SUCCESS, message, data);
    }

    public static <T> Result<T> fail(int code, String message) {
        return new Result<T>(code, message, null);
    }

    public static <T> Result<T> fail(String message) {
        return new Result<T>(CODE_ERROR, message, null);
    }

    public int getCode() {
        return code;
    }

    public void setCode(int code) {
        this.code = code;
    }

    public String getMessage() {
        return message;
    }

    public void setMessage(String message) {
        this.message = message;
    }

    public T getData() {
        return data;
    }

    public void setData(T data) {
        this.data = data;
    }
}
