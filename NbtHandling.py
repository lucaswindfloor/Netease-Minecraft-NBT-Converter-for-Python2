# -*- coding: utf-8 -*-
# Minecraft Netease Mod API NBT 与玩家可读 NBT 格式转换脚本

import re
import json

# NBT 类型映射表
# 该字典用于将__type__ ID映射到其类型名称
NBT_TYPE_MAP = {
    0: "TAG_End",
    1: "TAG_Byte",
    2: "TAG_Short",  # 附魔ID和等级使用的类型
    3: "TAG_Int",
    4: "TAG_Long",
    5: "TAG_Float",
    6: "TAG_Double",
    7: "TAG_Byte_Array",
    8: "TAG_String",
    9: "TAG_List",
    10: "TAG_Compound",
    11: "TAG_Int_Array",
    12: "TAG_Long_Array"
}

# 玩家可读 NBT 后缀到 __type__ ID 的映射
# 支持大小写后缀
TYPE_SUFFIX_MAP = {
    'b': 1,  # TAG_Byte
    'B': 1,
    's': 2,  # TAG_Short
    'S': 2,
    'i': 3,  # TAG_Int
    'I': 3,
    'l': 4,  # TAG_Long
    'L': 4,
    'f': 5,  # TAG_Float
    'F': 5,
    'd': 6,  # TAG_Double
    'D': 6,
}

def parse_readable_nbt_string(nbt_string):
    """
    解析玩家可读的NBT字符串。
    此函数现在支持两种顶层格式：
    1. 键名:值 (有名标签，如 'Items:[{...}]')
    2. {键名:值, ...} (无名Compound，如 '{Items:[{...}]}')
    """
    nbt_string = nbt_string.strip()

    try:
        # 尝试匹配有名标签格式
        match = re.match(r"([a-zA-Z0-9_]+)\s*:", nbt_string)
        if match:
            key = match.group(1)
            i = match.end()
            value, _ = _parse_value(nbt_string, i)
            # 返回一个字典来表示顶层有名标签
            return {key: value}
        else:
            # 如果不是有名标签，则检查是否是无名Compound
            if not nbt_string.startswith('{') or not nbt_string.endswith('}'):
                raise ValueError("无效的NBT格式：顶级标签必须是有名标签或以 {} 包裹")

            # 调用核心递归解析器
            parsed_dict, _ = _parse_compound(nbt_string, 1)
            return parsed_dict
    except ValueError as e:
        print("格式化错误：{0}".format(e))
        return {}

def _parse_compound(nbt_string, start_index):
    """
    递归解析一个复合类型 (TAG_Compound)。
    它只处理键值对，并确保每个元素都是有名的。
    """
    result = {}
    i = start_index
    while i < len(nbt_string) and nbt_string[i] != '}':
        i = _skip_whitespace(nbt_string, i)
        if nbt_string[i] == '}':
            break

        # 匹配键名，只接受字母、数字和下划线
        match_key = re.match(r"([a-zA-Z0-9_]+)\s*:", nbt_string[i:])
        if not match_key:
            raise ValueError("TAG_Compound 内只能添加有名TAG，在索引 {0} 处发现无名TAG".format(i))

        key = match_key.group(1)
        i += match_key.end()

        # 解析键对应的值
        value, i = _parse_value(nbt_string, i)
        result[key] = value

        i = _skip_whitespace(nbt_string, i)
        if i < len(nbt_string) and nbt_string[i] == ',':
            i += 1

    if i >= len(nbt_string) or nbt_string[i] != '}':
        raise ValueError("复合类型 {} 括号不匹配".format())

    return result, i + 1

def _parse_list(nbt_string, start_index):
    """
    递归解析一个列表类型 (TAG_List)。
    它只处理无名元素，并确保列表中没有键值对。
    """
    result = []
    i = start_index
    while i < len(nbt_string) and nbt_string[i] != ']':
        i = _skip_whitespace(nbt_string, i)
        if nbt_string[i] == ']':
            break

        # 检查是否有名标签，如果匹配到则抛出错误
        if re.match(r"([a-zA-Z0-9_']+)\s*:", nbt_string[i:]):
            raise ValueError("TAG_List 内只能添加无名TAG，在索引 {0} 处发现有名TAG".format(i))

        value, i = _parse_value(nbt_string, i)
        result.append(value)

        i = _skip_whitespace(nbt_string, i)
        if i < len(nbt_string) and nbt_string[i] == ',':
            i += 1

    if i >= len(nbt_string) or nbt_string[i] != ']':
        raise ValueError("列表类型 [] 括号不匹配".format())

    return result, i + 1

def _parse_byte_array(nbt_string, start_index):
    """
    解析一个字节数组类型 (TAG_Byte_Array)。
    """
    result = []
    # 匹配 "B;" 前缀
    i = start_index
    i = _skip_whitespace(nbt_string, i)
    if not nbt_string[i:].startswith('B;'):
        raise ValueError("TAG_Byte_Array 格式错误，缺少 'B;' 前缀")

    i += 2
    while i < len(nbt_string) and nbt_string[i] != ']':
        i = _skip_whitespace(nbt_string, i)
        if nbt_string[i] == ']':
            break

        # 匹配字节值，确保它们是带有b或B后缀的数字
        match = re.match(r"(-?\d+)[bB]", nbt_string[i:])
        if not match:
            raise ValueError("TAG_Byte_Array 内元素格式错误，在索引 {0} 处".format(i))

        byte_val = int(match.group(1))
        # 根据 NBT 规则，Byte 类型是 8位有符号整数
        if not (-128 <= byte_val <= 127):
            raise ValueError("TAG_Byte 值超出范围（-128 到 127）")

        result.append((byte_val, 1)) # TAG_Byte
        i += match.end()

        i = _skip_whitespace(nbt_string, i)
        if i < len(nbt_string) and nbt_string[i] == ',':
            i += 1

    if i >= len(nbt_string) or nbt_string[i] != ']':
        raise ValueError("字节数组类型 [B;] 括号不匹配".format())

    return result, i + 1

def _parse_value(nbt_string, start_index):
    """
    解析一个值，根据其前缀选择合适的解析器。
    """
    i = _skip_whitespace(nbt_string, start_index)

    if nbt_string[i] == '{':
        return _parse_compound(nbt_string, i + 1)
    elif nbt_string[i] == '[':
        if nbt_string[i+1:].strip().startswith('B;'):
            return _parse_byte_array(nbt_string, i + 1)
        else:
            return _parse_list(nbt_string, i + 1)
    elif nbt_string[i] == "'":
        # 仅处理单引号字符串
        quote_char = nbt_string[i]
        end_index = i + 1
        value_chars = []
        while end_index < len(nbt_string):
            char = nbt_string[end_index]
            if char == '\\':
                if end_index + 1 < len(nbt_string) and nbt_string[end_index + 1] in [quote_char, '\\']:
                    value_chars.append(nbt_string[end_index + 1])
                    end_index += 2
                else:
                    value_chars.append(char)
                    end_index += 1
            elif char == quote_char:
                return ("".join(value_chars), 8), end_index + 1
            else:
                value_chars.append(char)
                end_index += 1
        raise ValueError("未闭合的引号，在索引 {0} 处".format(i))
    else:
        # 解析无引号的简单值
        match = re.match(r"[^,\}\]:]+", nbt_string[i:])
        if not match:
            raise ValueError("无效的标记，在索引 {0} 处".format(i))

        value_part = match.group(0).strip()
        value_tuple = _parse_simple_value(value_part)
        return value_tuple, i + len(match.group(0))

def _parse_simple_value(value_part):
    """
    解析一个简单的NBT值字符串。
    """
    if not value_part:
        return None, 0

    # 规则1: 尝试解析为带有类型后缀的数字
    if len(value_part) > 1 and value_part[-1] in TYPE_SUFFIX_MAP:
        suffix = value_part[-1]
        val_str = value_part[:-1]
        type_id = TYPE_SUFFIX_MAP[suffix]
        try:
            if '.' in val_str or 'E' in val_str.upper():
                return (float(val_str), type_id)
            return (int(val_str), type_id)
        except (ValueError, IndexError):
            # 解析失败，继续尝试下一个规则
            pass

    # 规则2: 尝试解析为常规数字 (不带后缀)
    try:
        # 优先解析为整数
        return (int(value_part), 3)
    except ValueError:
        # 如果不是整数，尝试解析为浮点数
        try:
            return (float(value_part), 5)
        except ValueError:
            # 规则3: 如果所有尝试都失败，最终判定为字符串
            return (value_part, 8)


def _skip_whitespace(s, i):
    while i < len(s) and s[i].isspace():
        i += 1
    return i

def readable_to_api(readable_nbt):
    """
    将玩家可读的NBT格式转换为Mod API格式。
    """
    api_nbt = {}
    for key, value in readable_nbt.items():
        if isinstance(value, dict):
            api_nbt[key] = readable_to_api(value)
        elif isinstance(value, list):
            new_list = []
            is_byte_array = len(value) > 0 and isinstance(value[0], tuple) and value[0][1] == 1
            if is_byte_array:
                # 这是一个 TAG_Byte_Array,需要特殊处理
                api_nbt[key] = {
                    "__type__": 7,
                    "__value__": [item[0] for item in value]
                }
            else:
                for item in value:
                    if isinstance(item, tuple) and len(item) == 2:
                        val, type_id = item
                        new_list.append({"__type__": type_id, "__value__": val})
                    elif isinstance(item, dict):
                        new_list.append(readable_to_api(item))
                    elif isinstance(item, str):
                        new_list.append({"__type__": 8, "__value__": item})
                    elif isinstance(item, int):
                        new_list.append({"__type__": 3, "__value__": item})
                    elif isinstance(item, float):
                        new_list.append({"__type__": 5, "__value__": item})

                api_nbt[key] = new_list
        else:
            if isinstance(value, tuple) and len(value) == 2:
                val, type_id = value
                api_nbt[key] = {"__type__": type_id, "__value__": val}
            else:
                val, type_id = _parse_simple_value(str(value))
                api_nbt[key] = {"__type__": type_id, "__value__": val}

    return api_nbt

def api_to_readable(api_nbt):
    """
    将Mod API格式的NBT转换为玩家可读的NBT字符串。
    """
    def _to_string(api_data):
        if isinstance(api_data, dict):
            if "__type__" in api_data:
                data_type = api_data["__type__"]
                data_value = api_data["__value__"]

                if data_type == 8:
                    # 现在只使用单引号作为包裹符号
                    if re.search(r"[\s,'{}\[\]:]", str(data_value)):
                        # 转义单引号
                        escaped_value = str(data_value).replace("\\", "\\\\").replace("'", "\\'")
                        return "'{0}'".format(escaped_value)
                    else:
                        return str(data_value)
                else:
                    suffix = next((s for s, t_id in TYPE_SUFFIX_MAP.items() if t_id == data_type), '')
                    if isinstance(data_value, float):
                        return "{0}{1}".format(data_value, suffix)
                    return "{0}{1}".format(data_value, suffix)
            else:
                compound_parts = ["{0}:{1}".format(k, _to_string(v)) for k, v in api_data.items()]
                return "{" + ",".join(compound_parts) + "}"
        elif isinstance(api_data, list):
            list_parts = [_to_string(item) for item in api_data]
            return "[" + ",".join(list_parts) + "]"
        else:
            return str(api_data)

    top_level_parts = ["{0}:{1}".format(key, _to_string(data)) for key, data in api_nbt.items()]

    return "{" + ",".join(top_level_parts) + "}"


