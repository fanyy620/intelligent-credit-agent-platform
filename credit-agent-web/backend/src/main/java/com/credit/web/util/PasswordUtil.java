package com.credit.web.util;

import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.security.SecureRandom;

/**
 * 密码工具：盐值 + MD5 哈希（教学场景够用；生产建议升级 BCrypt/Argon2）。
 * 存储格式：password 列存 md5(salt + 明文)，salt 列存随机盐。
 */
public final class PasswordUtil {

    private static final String SALT_CHARS = "abcdef0123456789";
    private static final SecureRandom RANDOM = new SecureRandom();

    private PasswordUtil() {
    }

    /** 生成 6 位随机盐 */
    public static String generateSalt() {
        StringBuilder sb = new StringBuilder(6);
        for (int i = 0; i < 6; i++) {
            sb.append(SALT_CHARS.charAt(RANDOM.nextInt(SALT_CHARS.length())));
        }
        return sb.toString();
    }

    /** md5(salt + rawPassword)，32 位小写十六进制 */
    public static String hash(String salt, String rawPassword) {
        return md5(salt + rawPassword);
    }

    /** 校验明文与库内哈希是否匹配 */
    public static boolean verify(String salt, String rawPassword, String expectedHash) {
        return hash(salt, rawPassword).equalsIgnoreCase(expectedHash);
    }

    private static String md5(String text) {
        try {
            MessageDigest md = MessageDigest.getInstance("MD5");
            byte[] digest = md.digest(text.getBytes(StandardCharsets.UTF_8));
            StringBuilder sb = new StringBuilder(32);
            for (byte b : digest) {
                sb.append(String.format("%02x", b & 0xff));
            }
            return sb.toString();
        } catch (NoSuchAlgorithmException e) {
            throw new IllegalStateException("JDK 缺少 MD5 实现", e);
        }
    }
}
