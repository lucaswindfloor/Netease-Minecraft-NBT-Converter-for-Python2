# -*- coding: utf-8 -*-
# Minecraft Netease Mod API NBT 与玩家可读 NBT 格式转换脚本 (Python 3)

import re
import json

# --- 1. NBT 类型和后缀映射 ---
# NBT 类型ID映射到类型名称
NBT_TYPE_MAP = {
    0: "TAG_End", 1: "TAG_Byte", 2: "TAG_Short", 3: "TAG_Int",
    4: "TAG_Long", 5: "TAG_Float", 6: "TAG_Double", 7: "TAG_Byte_Array",
    8: "TAG_String", 9: "TAG_List", 10: "TAG_Compound", 11: "TAG_Int_Array",
    12: "TAG_Long_Array"
}

# 玩家可读 NBT 后缀到 __type__ ID 的映射
TYPE_SUFFIX_MAP = {
    'b': 1, 'B': 1, 's': 2, 'S': 2, 'i': 3, 'I': 3, 'l': 4,
    'L': 4, 'f': 5, 'F': 5, 'd': 6, 'D': 6,
}

# 特殊键名及其玩家可读格式的映射，用于反向转换
SPECIAL_KEYS = {
    'minecraft:item_lock': {
        'lock_in_inventory': '1b',
        'lock_in_slot': '2b'
    },
    'minecraft:keep_on_death': {
        '': '1b'
    }
}

# --- 2. 辅助函数 ---
def _skip_whitespace(s, i):
    """跳过字符串中的所有空白字符"""
    while i < len(s) and s[i].isspace():
        i += 1
    return i

def _parse_simple_value(value_part):
    """
    解析一个简单的NBT值字符串，并推断其类型。
    返回一个 (值, 类型ID) 元组。
    """
    if not value_part:
        return None, 0

    # 规则1: 尝试解析为带有类型后缀的数字
    if len(value_part) > 1 and value_part[-1].lower() in TYPE_SUFFIX_MAP:
        suffix = value_part[-1].lower()
        val_str = value_part[:-1]
        type_id = TYPE_SUFFIX_MAP[suffix]
        try:
            if '.' in val_str or 'e' in val_str.lower():
                return float(val_str), type_id
            return int(val_str), type_id
        except (ValueError, IndexError):
            pass  # 解析失败，继续尝试下一个规则

    # 规则2: 尝试解析为常规数字 (不带后缀)
    try:
        # 优先解析为整数
        return int(value_part), 3  # TAG_Int
    except ValueError:
        try:
            # 如果不是整数，尝试解析为浮点数
            return float(value_part), 5  # TAG_Float
        except ValueError:
            # 规则3: 如果所有尝试都失败，最终判定为字符串
            return value_part, 8 # TAG_String

# --- 3. 核心解析函数 ---
def _parse_value(nbt_string, start_index):
    """
    根据其前缀选择合适的解析器。
    返回 (值, 类型ID)
    """
    i = _skip_whitespace(nbt_string, start_index)
    if i >= len(nbt_string):
        raise ValueError("在索引 {0} 处意外的输入结束".format(start_index))

    char = nbt_string[i]
    if char == '{':
        return _parse_compound(nbt_string, i + 1)
    elif char == '[':
        # 检查是否为数组类型（如 '[B;', '[I;', '[L;')
        peek_str = nbt_string[i+1:].lstrip()
        if peek_str.startswith('B;') or peek_str.startswith('I;') or peek_str.startswith('L;'):
            return _parse_array(nbt_string, i + 1)
        else:
            return _parse_list(nbt_string, i + 1)
    elif char == "'":
        # 解析单引号字符串
        end_index = i + 1
        value_chars = []
        while end_index < len(nbt_string):
            current_char = nbt_string[end_index]
            if current_char == '\\':
                # 处理转义字符
                if end_index + 1 < len(nbt_string):
                    escaped_char_next = nbt_string[end_index + 1]
                    if escaped_char_next == 'n':
                        value_chars.append('\n')
                    elif escaped_char_next == 't':
                        value_chars.append('\t')
                    elif escaped_char_next == 'r':
                        value_chars.append('\r')
                    elif escaped_char_next == "'":
                        value_chars.append("'")
                    elif escaped_char_next == '"':
                        value_chars.append('"')
                    else:
                        value_chars.append(escaped_char_next)
                    end_index += 2
                else:
                    value_chars.append(current_char)
                    end_index += 1
            elif current_char == "'":
                return {"__type__": 8, "__value__": "".join(value_chars)}, end_index + 1
            else:
                value_chars.append(current_char)
                end_index += 1
        raise ValueError("未闭合的单引号在索引 {0} 处".format(i))
    else:
        # 解析无引号的简单值
        end_idx = i
        while end_idx < len(nbt_string):
            c = nbt_string[end_idx]
            if c in [',', '}', ']']:
                break
            if c == ':' and nbt_string[end_idx-1] != '\\':
                break
            end_idx += 1

        value_part = nbt_string[i:end_idx].strip()
        if not value_part:
            raise ValueError("在索引 {0} 处发现无效值".format(i))

        val, type_id = _parse_simple_value(value_part)
        return {"__type__": type_id, "__value__": val}, end_idx

def _parse_compound(nbt_string, start_index):
    """递归解析一个复合类型 (TAG_Compound)"""
    result = {}
    i = _skip_whitespace(nbt_string, start_index)
    if i >= len(nbt_string) or nbt_string[i] == '}':
        return result, i + 1

    while i < len(nbt_string):
        # 匹配键名，现在支持带冒号的键名和转义
        key_end = i
        escaped = False
        while key_end < len(nbt_string):
            c = nbt_string[key_end]
            if escaped:
                escaped = False
            elif c == '\\':
                escaped = True
            elif c == ':' and not escaped:
                break
            key_end += 1

        if key_end >= len(nbt_string) or nbt_string[key_end] != ':':
            raise ValueError("在索引 {0} 处找不到键名和值的冒号分隔符".format(i))

        # 还原转义字符
        key = nbt_string[i:key_end].strip().replace('\\:', ':').replace('\\{', '{').replace('\\}', '}').replace('\\[', '[').replace('\\]', ']').replace("\\'", "'").replace('\\"', '"').replace('\\\\', '\\')
        i = key_end + 1

        value, next_i = _parse_value(nbt_string, i)
        result[key] = value
        i = _skip_whitespace(nbt_string, next_i)

        if i < len(nbt_string) and nbt_string[i] == '}':
            return result, i + 1
        if i < len(nbt_string) and nbt_string[i] == ',':
            i += 1
        else:
            raise ValueError("在索引 {0} 处复合类型中缺少逗号或右括号".format(i))
    raise ValueError("未闭合的复合类型")

def _parse_list(nbt_string, start_index):
    """递归解析一个列表类型 (TAG_List)"""
    result = []
    i = _skip_whitespace(nbt_string, start_index)
    if i >= len(nbt_string) or nbt_string[i] == ']':
        return result, i + 1

    while i < len(nbt_string):
        value, next_i = _parse_value(nbt_string, i)
        result.append(value)
        i = _skip_whitespace(nbt_string, next_i)

        if i < len(nbt_string) and nbt_string[i] == ']':
            return result, i + 1
        if i < len(nbt_string) and nbt_string[i] == ',':
            i += 1
        else:
            raise ValueError("在索引 {0} 处列表中缺少逗号或右中括号".format(i))
    raise ValueError("未闭合的列表")

def _parse_array(nbt_string, start_index):
    """解析一个数组类型 (TAG_Byte_Array, TAG_Int_Array, TAG_Long_Array)"""
    result = []
    i = _skip_whitespace(nbt_string, start_index)

    # 确定数组类型
    prefix = nbt_string[i:i+2]
    type_map = {'B;': 7, 'I;': 11, 'L;': 12}
    if prefix not in type_map:
        raise ValueError("在索引 {0} 处发现未知的数组前缀".format(i))

    array_type_id = type_map[prefix]
    i += 2
    i = _skip_whitespace(nbt_string, i)
    if i >= len(nbt_string) or nbt_string[i] == ']':
        return {"__type__": array_type_id, "__value__": result}, i + 1

    while i < len(nbt_string):
        end_idx = i
        while end_idx < len(nbt_string) and nbt_string[end_idx] not in [',', ']']:
            end_idx += 1

        value_part = nbt_string[i:end_idx].strip()
        if not value_part:
            raise ValueError("在索引 {0} 处发现无效的数组元素".format(i))

        val, val_type_id = _parse_simple_value(value_part)

        # 验证数组元素类型是否一致
        if (val_type_id != 1 and array_type_id == 7) or \
                (val_type_id != 3 and array_type_id == 11) or \
                (val_type_id != 4 and array_type_id == 12):
            raise ValueError("数组元素类型不匹配。在索引 {0} 处，期望 {1} 但发现 {2}".format(i, NBT_TYPE_MAP[array_type_id], NBT_TYPE_MAP[val_type_id]))

        result.append(val)
        i = _skip_whitespace(nbt_string, end_idx)

        if i < len(nbt_string) and nbt_string[i] == ']':
            return {"__type__": array_type_id, "__value__": result}, i + 1
        if i < len(nbt_string) and nbt_string[i] == ',':
            i += 1
        else:
            raise ValueError("在索引 {0} 处数组中缺少逗号或右中括号".format(i))
    raise ValueError("未闭合的数组")

def parse_readable_nbt(nbt_string):
    """
    解析玩家可读的NBT字符串到Python字典（类似于Mod API格式）。
    支持有名标签（`key:value`）和复合标签（`{key:value}`）作为顶层。
    """
    nbt_string = nbt_string.strip()
    if not nbt_string:
        return {}

    # 尝试匹配有名标签格式
    match = re.match(r"([a-zA-Z0-9_:]+)\s*:", nbt_string)
    if match:
        key = match.group(1).strip()
        i = match.end()
        value, _ = _parse_value(nbt_string, i)
        return {key: value}
    else:
        # 如果不是有名标签，检查是否是无名复合标签
        if not nbt_string.startswith('{') or not nbt_string.endswith('}'):
            raise ValueError("无效的NBT格式：顶级标签必须是有名标签或以 {} 包裹")
        parsed_dict, _ = _parse_compound(nbt_string, 1)
        return parsed_dict

# --- 4. 转换函数 ---
def api_to_readable(api_nbt):
    """
    将Mod API格式的NBT字典转换为玩家可读的NBT字符串。
    """
    def _to_string(data):
        # 检查是否为叶子节点
        if isinstance(data, (str, int, float, bool)):
            return str(data)

        if isinstance(data, dict) and "__type__" in data and "__value__" in data:
            data_type = data["__type__"]
            data_value = data["__value__"]

            if data_type == 8:  # TAG_String
                # 对字符串中的特殊字符进行转义
                escaped_value = str(data_value).replace('\n', '\\n').replace('\t', '\\t').replace('\\', '\\\\').replace("'", "\\'")

                # 如果包含特殊字符或空格，则使用单引号包裹
                if re.search(r"[\s,:{}'\[\]]", str(data_value)):
                    return "'{0}'".format(escaped_value)
                else:
                    return str(data_value)

            elif data_type in [7, 11, 12]:  # TAG_Array
                return _to_string(data_value)

            else:
                # 添加类型后缀
                suffix = next((s for s, t_id in TYPE_SUFFIX_MAP.items() if t_id == data_type), '')
                return "{0}{1}".format(data_value, suffix.lower())

        elif isinstance(data, dict):
            # 复合类型
            parts = []
            for key, value in data.items():

                # 检查特殊键
                is_special_key_conversion = False
                if key in SPECIAL_KEYS:
                    mode_data = value.get('mode', {}) if isinstance(value, dict) else value
                    mode_value = mode_data.get('__value__', '') if isinstance(mode_data, dict) else mode_data
                    if mode_value in SPECIAL_KEYS[key]:
                        parts.append("{0}:{1}".format(key, SPECIAL_KEYS[key][mode_value]))
                        is_special_key_conversion = True

                if not is_special_key_conversion:
                    # 对键名中的特殊字符进行转义
                    escaped_key = str(key).replace("\\", "\\\\").replace("'", "\\'").replace(":", "\\:").replace("{", "\\{").replace("}", "\\}").replace("[", "\\[").replace("]", "\\]")
                    parts.append("{0}:{1}".format(escaped_key, _to_string(value)))

            return "{" + ",".join(parts) + "}"

        elif isinstance(data, list):
            # 列表类型
            list_parts = [_to_string(item) for item in data]
            return "[" + ",".join(list_parts) + "]"

        else:
            return str(data)

    if isinstance(api_nbt, dict) and len(api_nbt) == 1:
        key = list(api_nbt.keys())[0]
        value = api_nbt[key]
        return "{0}:{1}".format(key, _to_string(value))
    else:
        return _to_string(api_nbt)

def readable_to_api(readable_nbt):
    """
    将玩家可读的NBT字典转换为Mod API格式。
    """
    api_nbt = {}
    for key, value_obj in readable_nbt.items():
        if isinstance(value_obj, dict):
            api_nbt[key] = readable_to_api(value_obj)
        elif isinstance(value_obj, list):
            api_nbt[key] = [readable_to_api(item) for item in value_obj]
        else:
            api_nbt[key] = value_obj
    return api_nbt


# --- 5. 示例用法 ---
if __name__ == '__main__':
    print("--- 玩家可读 NBT 到 Mod API NBT (V7) ---")

    # 示例1: 包含转义字符和特殊键的复杂 NBT
    readable_input_str_complex = """
    {
        Items:[
            {
                Slot:0b,
                tag:{
                    display:{
                        Name:'一个转义\\:名称',
                        Lore:['\\t\\n一个转义的\\'','锁在背包里']
                    },
                    minecraft\:item_lock:{mode:'lock_in_inventory'},
                    minecraft\:keep_on_death:{}
                }
            },
            {   slot:1b,
                tag:{
                    ench:[
                    ]
                }
            }
        ]
    }"""
    print("输入玩家可读NBT:\n" + readable_input_str_complex)
    try:
        parsed_dict = parse_readable_nbt(readable_input_str_complex)
        api_output = readable_to_api(parsed_dict)
        print("\n转换后的 Mod API NBT:")
        print(json.dumps(api_output, indent=4, ensure_ascii=False))
    except ValueError as e:
        print("\n解析错误: {0}".format(e))

    print("\n" + "="*50 + "\n")

    # 示例2: Mod API NBT 到玩家可读 NBT (反向转换)
    print("--- Mod API NBT 到玩家可读 NBT (V7) ---")
    api_input_dict = {
        "Items": [
            {
                "Slot": { "__type__": 1, "__value__": 0 },
                "tag": {
                    "display": {
                        "Name": { "__type__": 8, "__value__": "一个转义:名称" },
                        "Lore": [
                            { "__type__": 8, "__value__": "\t\n一个转义的'" },
                            { "__type__": 8, "__value__": "锁在背包里" }
                        ]
                    },
                    "minecraft:item_lock": {
                        "mode": { "__type__": 8, "__value__": "lock_in_inventory" }
                    },
                    "minecraft:keep_on_death": {
                        "mode": { "__type__": 8, "__value__": "" } # 这种形式也应被处理
                    }
                }
            }
        ]
    }

    print("输入 Mod API NBT:")
    print(json.dumps(api_input_dict, indent=4, ensure_ascii=False))

    try:
        readable_output = api_to_readable(api_input_dict)
        print("\n转换后的玩家可读 NBT:")
        print(readable_output)
    except ValueError as e:
        print("\n转换错误: {0}".format(e))
