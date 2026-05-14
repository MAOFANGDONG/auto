package com.example.{{ project_name_lower }}.exception;

/**
 * 业务异常
 * Service 层抛出，由 GlobalExceptionHandler 统一处理
 */
public class BusinessException extends RuntimeException {
    private int code;

    public BusinessException(String message) {
        super(message);
        this.code = 500;
    }

    public BusinessException(int code, String message) {
        super(message);
        this.code = code;
    }

    public int getCode() {
        return code;
    }

    public void setCode(int code) {
        this.code = code;
    }
}
