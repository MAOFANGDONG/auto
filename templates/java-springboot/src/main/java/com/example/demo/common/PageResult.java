package com.example.{{ project_name_lower }}.common;

import org.springframework.data.domain.Page;
import java.util.List;

/**
 * 分页响应体
 * 所有分页查询必须返回此类型
 */
public class PageResult<T> {
    private long total;
    private List<T> records;
    private int pageSize;
    private int page;

    /**
     * 从 Spring Page 对象构造
     */
    public static <T> PageResult<T> of(Page<T> page) {
        PageResult<T> result = new PageResult<>();
        result.setTotal(page.getTotalElements());
        result.setRecords(page.getContent());
        result.setPageSize(page.getSize());
        result.setPage(page.getNumber() + 1);
        return result;
    }

    /**
     * 从 Spring Page 对象构造，指定页码（从1开始）
     */
    public static <T> PageResult<T> of(Page<T> page, int pageNum) {
        PageResult<T> result = new PageResult<>();
        result.setTotal(page.getTotalElements());
        result.setRecords(page.getContent());
        result.setPageSize(page.getSize());
        result.setPage(pageNum);
        return result;
    }

    public long getTotal() {
        return total;
    }

    public void setTotal(long total) {
        this.total = total;
    }

    public List<T> getRecords() {
        return records;
    }

    public void setRecords(List<T> records) {
        this.records = records;
    }

    public int getPageSize() {
        return pageSize;
    }

    public void setPageSize(int pageSize) {
        this.pageSize = pageSize;
    }

    public int getPage() {
        return page;
    }

    public void setPage(int page) {
        this.page = page;
    }
}
