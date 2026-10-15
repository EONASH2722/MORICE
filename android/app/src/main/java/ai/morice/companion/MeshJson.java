package ai.morice.companion;

import org.json.JSONArray;
import org.json.JSONObject;
import org.json.JSONTokener;
import java.nio.ByteBuffer;
import java.nio.charset.CodingErrorAction;
import java.nio.charset.StandardCharsets;

/** Strict bounded parsing of authenticated, still-untrusted mesh data. */
final class MeshJson {
    static JSONObject parse(byte[] bytes) throws Exception {
        String text = StandardCharsets.UTF_8.newDecoder().onMalformedInput(CodingErrorAction.REPORT)
            .onUnmappableCharacter(CodingErrorAction.REPORT).decode(ByteBuffer.wrap(bytes)).toString();
        JSONTokener input = new JSONTokener(text);
        Object value = value(input, 0);
        if (!(value instanceof JSONObject) || input.nextClean() != 0) throw new SecurityException("Invalid JSON envelope.");
        return (JSONObject) value;
    }
    private static Object value(JSONTokener input, int depth) throws Exception {
        if (depth > 12) throw new SecurityException("JSON depth limit.");
        char token = input.nextClean();
        if (token == '"') {
            String result = input.nextString('"');
            if (result.length() > 200000) throw new SecurityException("JSON string limit.");
            return result;
        }
        if (token == '{') {
            JSONObject result = new JSONObject();
            token = input.nextClean(); if (token == '}') return result; input.back();
            while (true) {
                if (input.nextClean() != '"') throw new SecurityException("JSON keys must be quoted.");
                String key = input.nextString('"');
                if (key.length() > 200000 || result.has(key) || result.length() >= 128 || input.nextClean() != ':') throw new SecurityException("Invalid/duplicate JSON key.");
                result.put(key, value(input, depth + 1));
                token = input.nextClean(); if (token == '}') return result;
                if (token != ',') throw new SecurityException("Invalid JSON object.");
            }
        }
        if (token == '[') {
            JSONArray result = new JSONArray();
            token = input.nextClean(); if (token == ']') return result; input.back();
            while (true) {
                if (result.length() >= 256) throw new SecurityException("JSON array limit.");
                result.put(value(input, depth + 1));
                token = input.nextClean(); if (token == ']') return result;
                if (token != ',') throw new SecurityException("Invalid JSON array.");
            }
        }
        StringBuilder primitive = new StringBuilder();
        while (token != 0 && token != ',' && token != '}' && token != ']' && !Character.isWhitespace(token)) {
            primitive.append(token); if (primitive.length() > 128) throw new SecurityException("JSON number limit."); token = input.next();
        }
        if (token != 0) input.back();
        String text = primitive.toString();
        if (text.equals("true")) return Boolean.TRUE;
        if (text.equals("false")) return Boolean.FALSE;
        if (text.equals("null")) return JSONObject.NULL;
        if (!text.matches("-?(0|[1-9][0-9]*)(\\.[0-9]+)?([eE][+-]?[0-9]+)?")) throw new SecurityException("Invalid JSON primitive.");
        Number number;
        if (text.matches("-?(0|[1-9][0-9]*)")) {
            long integer = Long.parseLong(text);
            if (integer >= Integer.MIN_VALUE && integer <= Integer.MAX_VALUE) number = Integer.valueOf((int) integer);
            else number = Long.valueOf(integer);
        } else number = Double.valueOf(text);
        if (!Double.isFinite(number.doubleValue())) throw new SecurityException("Invalid JSON number.");
        return number;
    }
}
