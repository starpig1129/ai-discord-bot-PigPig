import sympy
async def calculate_math(message_to_edit, message, expression):
    try:
        sympy_expr = sympy.sympify(expression)
        result = sympy.N(sympy_expr)
        print(f'sympy:{result}')
        return f'sympy result:{result}'
    except sympy.SympifyError as e:
        return "無法計算: {str(e)}"
    except Exception as e:
        return "計算錯誤: {str(e)}"