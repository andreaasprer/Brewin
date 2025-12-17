from intbase import InterpreterBase, ErrorType
from brewparse import parse_program
import enum


class Type(enum.Enum):
    NIL = 0
    INT = 1
    STRING = 2
    BOOL = 3
    OBJECT = 4
    VOID = 5


class Value:
    def __init__(self, t=None, v=None):
        if t is None:
            self.t = Type.NIL
            self.v = None
        else:
            self.t = t
            self.v = v


class BrewinObject:
    def __init__(self):
        self.fields = {}

    def get_field(self, key):
        if key not in self.fields:
            super().error(ErrorType.NAME_ERROR, f"field {key} not found")
        return self.fields[key]
    
    def set_field(self, key, value):
        self.fields[key] = value

    def has_field(self, key):
        return key in self.fields


class Reference:
    def __init__(self, env, var_name):
        self.env = env
        self.var_name = var_name
    
    def get(self):
        if '.' not in self.var_name:
            return self.env.get(self.var_name)
        else:
            # handle objects too 
            parts = self.var_name.split('.')
            curr = self.env.get(parts[0])
            for p in parts[1:]:
                if curr.t != Type.OBJECT or curr.v is None:
                    return None
                if not curr.v.has_field(p):
                    return None
                curr = curr.v.get_field(p)
            return curr
    
    def set(self, value):
        if '.' not in self.var_name:
            self.env.set(self.var_name, value)
        else:
            # handle objects too
            parts = self.var_name.split('.')
            curr = self.env.get(parts[0])
            for p in parts[1:-1]:
                curr = curr.v.get_field(p)
            curr.v.set_field(parts[-1], value)


class Environment:
    def __init__(self):
        self.env = []

    def enter_block(self):
        self.env[-1].append({})

    def exit_block(self):
        self.env[-1].pop()

    def enter_func(self):
        self.env.append([{}])

    def exit_func(self):
        self.env.pop()

    # define new variable at function scope
    def fdef(self, varname):
        if self.exists(varname):
            return False
        top_env = self.env[-1]
        top_env[0][varname] = Value()
        return True

    # define new variable at block scope
    def bdef(self, varname):
        if self.exists(varname):
            return False
        top_env = self.env[-1]
        top_env[-1][varname] = Value() # add to current block
        return True

    def exists(self, varname):
        for block in self.env[-1]:
            if varname in block:
                return True
        return False

    def get(self, varname):
        top_env = self.env[-1]
        for block in top_env:
            if varname in block:
                val = block[varname]

                if type(val) == Reference:
                    return val.get()
                return val
        return None

    def set(self, varname, value):
        if not self.exists(varname):
            return False
        top_env = self.env[-1]
        for block in top_env:
            if varname in block:
                val = block[varname]

                if type(val) == Reference:
                    val.set(value)
                else:
                    block[varname] = value
                return True
        return True


class Interpreter(InterpreterBase):
    def __init__(self, console_output=True, inp=None, trace_output=False):
        super().__init__(console_output, inp)
        self.funcs = {}
        self.env = Environment()
        self.bops = {"+", "-", "*", "/", "==", "!=", ">", ">=", "<", "<=", "||", "&&"}

    def run(self, program):
        ast = parse_program(program)
        self.__create_function_table(ast)
        self.__run_fcall(self.__get_function("main"))

    def __create_function_table(self, ast):
        """Allow multiple functions but different parameter type signatures"""
        self.funcs = {}
        for func in ast.get("functions"):
            func_name = func.get("name")

            # get function and parameter types
            if func_name != "main":
                self.__get_type_from_suffix(func_name)
            arg_types = tuple(
                self.__get_type_from_suffix(arg.get("name")) for arg in func.get("args")
            )

            # validate parameters. Prevent VOID types
            for arg in func.get("args"):
                name = arg.get("name")
                type = self.__get_type_from_suffix(name)

                if type == Type.VOID:
                    super().error(ErrorType.TYPE_ERROR, "formal parameters cannot be VOID type")

            # prevent duplicates
            if (func_name, arg_types) in self.funcs:
                super().error(ErrorType.NAME_ERROR, f"{func_name} already exists. Duplicate functions not allowed")
            self.funcs[(func_name, arg_types)] = func

    def __get_function(self, name, arg_types=()):
        if (name, arg_types) not in self.funcs:
            super().error(ErrorType.NAME_ERROR, "function not found")
        return self.funcs[(name, arg_types)]

    def __run_vardef(self, statement):
        name = statement.get("name")

        var_type = self.__get_type_from_suffix(name)

        if var_type == Type.VOID:
            super().error(ErrorType.TYPE_ERROR, "variable cannot be VOID type")

        if not self.env.fdef(name):
            super().error(ErrorType.NAME_ERROR, "variable already defined")

        # initialize variable with default value for its type
        default_val = self.__get_default_value(var_type)
        self.env.set(name, default_val)

    def __run_bvardef(self, statement):
        name = statement.get("name")

        var_type = self.__get_type_from_suffix(name)

        if var_type == Type.VOID:
            super().error(ErrorType.TYPE_ERROR, "variable cannot be VOID type")
            
        if not self.env.bdef(name):
            super().error(ErrorType.NAME_ERROR, "variable already defined")

        # initialize variable at block scope with default value for its type
        default_val = self.__get_default_value(var_type)
        self.env.set(name, default_val)

    def __run_assign(self, statement):
        name = statement.get("var")

        # regular values
        if '.' not in name:
            type = self.__get_type_from_suffix(name)
            value = self.__eval_expr(statement.get("expression"))
            self.__validate_type(type, value)
            if not self.env.set(name, value):
                super().error(ErrorType.NAME_ERROR, "variable not defined")
        else: # object field assignment
            self.__assign_dotted(name, statement.get("expression"))

    def __handle_input(self, fcall_name, args):
        """Handle inputi and inputs function calls"""
        if len(args) > 1:
            super().error(ErrorType.NAME_ERROR, "too many arguments for input function")

        if args:
            self.__handle_print(args)

        res = super().get_input()

        return (
            Value(Type.INT, int(res))
            if fcall_name == "inputi"
            else Value(Type.STRING, res)
        )

    def __handle_print(self, args):
        """Handle print function calls"""
        out = ""

        for arg in args:
            c_out = self.__eval_expr(arg)
            if c_out.t == Type.BOOL:
                out += str(c_out.v).lower()
            else:
                out += str(c_out.v)

        super().output(out)

        return Value(Type.VOID, None)

    def __run_fcall(self, func_call_ast):
        fcall_name, args = func_call_ast.get("name"), func_call_ast.get("args")

        if fcall_name == "inputi" or fcall_name == "inputs":
            return self.__handle_input(fcall_name, args)

        if fcall_name == "print":
            return self.__handle_print(args)

        actual_args = [self.__eval_expr(a) for a in args]
        arg_types = tuple(arg.t for arg in actual_args)
        
        func_def = self.__get_function(fcall_name, arg_types)
        formal_arg_nodes = func_def.get("args")

        self.env.enter_func()
        
        # support pass by ref and pass by val
        for i, (formal_node, actual_val) in enumerate(zip(formal_arg_nodes, actual_args)):
            formal_name = formal_node.get("name")
            is_ref = formal_node.get("ref")
            
            self.env.fdef(formal_name)
            
            if is_ref:
                arg_expr = args[i]
                if arg_expr.elem_type == 'qname':
                    var_name = arg_expr.get('name')
                    # point to caller's scope
                    caller_env = Environment()
                    caller_env.env = self.env.env[:-1]
                    
                    top_env = self.env.env[-1]
                    top_env[0][formal_name] = Reference(caller_env, var_name)
                else:
                    super().error(ErrorType.TYPE_ERROR, "not valid reference parameter")
            else:  # pass by val
                self.env.set(formal_name, actual_val)
        
        res, _ = self.__run_statements(func_def.get("statements"))
        self.env.exit_func()

        # return default value for the declared return type
        func_ret_type = self.__get_type_from_suffix(fcall_name)
        if res.t == Type.NIL:
            res = self.__get_default_value(func_ret_type)
        else: # check consistency with types
            self.__validate_type(func_ret_type, res)

        return res

    def __run_if(self, statement):
        cond = self.__eval_expr(statement.get("condition"))

        if cond.t != Type.BOOL:
            super().error(ErrorType.TYPE_ERROR, "condition must be boolean")

        self.env.enter_block()

        res, ret = Value(), False

        if cond.v:
            res, ret = self.__run_statements(statement.get("statements"))
        elif statement.get("else_statements"):
            res, ret = self.__run_statements(statement.get("else_statements"))

        self.env.exit_block()

        return res, ret

    def __run_while(self, statement):
        res, ret = Value(), False

        while True:
            cond = self.__eval_expr(statement.get("condition"))

            if cond.t != Type.BOOL:
                super().error(ErrorType.TYPE_ERROR, "condition must be boolean")

            if not cond.v:
                break

            self.env.enter_block()
            res, ret = self.__run_statements(statement.get("statements"))
            self.env.exit_block()
            if ret:
                break

        return res, ret

    def __run_return(self, statement):
        expr = statement.get("expression")
        if expr:
            return (self.__eval_expr(expr), True)
        return (Value(), True)

    def __run_statements(self, statements):
        res, ret = Value(), False

        for statement in statements:
            kind = statement.elem_type

            if kind == self.VAR_DEF_NODE:
                self.__run_vardef(statement)
            elif kind == self.BVAR_DEF_NODE:
                self.__run_bvardef(statement)
            elif kind == "=":
                self.__run_assign(statement)
            elif kind == self.FCALL_NODE:
                self.__run_fcall(statement)
            elif kind == self.IF_NODE:
                res, ret = self.__run_if(statement)
                if ret:
                    break
            elif kind == self.WHILE_NODE:
                res, ret = self.__run_while(statement)
                if ret:
                    break
            elif kind == self.RETURN_NODE:
                res, ret = self.__run_return(statement)
                break

        return res, ret

    def __eval_binary_op(self, kind, vl, vr):
        """Evaluate binary operations"""
        tl, tr = vl.t, vr.t
        vl_val, vr_val = vl.v, vr.v

        if kind == "==":
            return Value(Type.BOOL, tl == tr and vl_val == vr_val)
        if kind == "!=":
            return Value(Type.BOOL, not (tl == tr and vl_val == vr_val))

        if tl == Type.STRING and tr == Type.STRING:
            if kind == "+":
                return Value(Type.STRING, vl_val + vr_val)

        if tl == Type.INT and tr == Type.INT:
            if kind == "+":
                return Value(Type.INT, vl_val + vr_val)
            if kind == "-":
                return Value(Type.INT, vl_val - vr_val)
            if kind == "*":
                return Value(Type.INT, vl_val * vr_val)
            if kind == "/":
                return Value(Type.INT, vl_val // vr_val)
            if kind == "<":
                return Value(Type.BOOL, vl_val < vr_val)
            if kind == "<=":
                return Value(Type.BOOL, vl_val <= vr_val)
            if kind == ">":
                return Value(Type.BOOL, vl_val > vr_val)
            if kind == ">=":
                return Value(Type.BOOL, vl_val >= vr_val)

        if tl == Type.BOOL and tr == Type.BOOL:
            if kind == "&&":
                return Value(Type.BOOL, vl_val and vr_val)
            if kind == "||":
                return Value(Type.BOOL, vl_val or vr_val)

        super().error(ErrorType.TYPE_ERROR, "invalid binary operation")

    def __eval_expr(self, expr):
        kind = expr.elem_type

        if kind == self.INT_NODE:
            return Value(Type.INT, expr.get("val"))

        if kind == self.STRING_NODE:
            return Value(Type.STRING, expr.get("val"))

        if kind == self.BOOL_NODE:
            return Value(Type.BOOL, expr.get("val"))

        if kind == self.NIL_NODE:
            return Value(Type.OBJECT, None)

        if kind == self.QUALIFIED_NAME_NODE:
            var_name = expr.get("name")

            # dereference if dotted
            if '.' in var_name:
                return self.__eval_dotted_names(var_name)
            
            if not self.env.exists(var_name):
                super().error(ErrorType.NAME_ERROR, "variable not defined")
            return self.env.get(var_name)

        if kind == self.FCALL_NODE:
            return self.__run_fcall(expr)

        if kind in self.bops:
            l, r = self.__eval_expr(expr.get("op1")), self.__eval_expr(expr.get("op2"))
            return self.__eval_binary_op(kind, l, r)

        if kind == self.NEG_NODE:
            o = self.__eval_expr(expr.get("op1"))
            if o.t == Type.INT:
                return Value(Type.INT, -o.v)

            super().error(ErrorType.TYPE_ERROR, "cannot negate non-integer")

        if kind == self.NOT_NODE:
            o = self.__eval_expr(expr.get("op1"))
            if o.t == Type.BOOL:
                return Value(Type.BOOL, not o.v)

            super().error(ErrorType.TYPE_ERROR, "cannot apply NOT to non-boolean")

        if kind == self.CONVERT_NODE:
            to_type = expr.get("to_type")
            value = self.__eval_expr(expr.get("expr"))
            return self.__convert_value(value, to_type)
        
        # object creation
        if kind == self.EMPTY_OBJ_NODE:
            return Value(Type.OBJECT, BrewinObject())

        raise Exception("should not get here!")
    

    def __get_type_from_suffix(self, name):
        """Get type from variable or function name suffix"""

        if name == "main":
            return Type.VOID
        
        last = name[-1]
        type_map = {
            'i': Type.INT,
            's': Type.STRING,
            'b': Type.BOOL,
            'o': Type.OBJECT,
            'v': Type.VOID,
        }

        if last not in type_map:
            super().error(ErrorType.TYPE_ERROR, "function name does not end with a valid type letter")

        return type_map[last]  

    def __get_default_value(self, type):
        """Get default value based on declared return type""" 
        default_map = {
            Type.INT: Value(Type.INT, 0),
            Type.STRING: Value(Type.STRING, ""),
            Type.BOOL: Value(Type.BOOL, False),
            Type.OBJECT: Value(Type.OBJECT, None), # nil
            Type.VOID: Value(Type.VOID, None), # void
        }

        if type not in default_map:
            super().error(ErrorType.TYPE_ERROR, "invalid type. Type does not have default value")
        
        return default_map[type]

    def __validate_type(self, type, value):
        """Check if value's type is the expected type"""
        if value.t != type:
            super().error(ErrorType.TYPE_ERROR, "incorrect type, types are mismatched.")

    def __convert_value(self, value, to_type):
        if to_type == "int":
            if value.t == Type.INT:
                return value
            elif value.t == Type.BOOL:
                return Value(Type.INT, 1 if value.v else 0)
            elif value.t == Type.STRING:
                # wrap around try/catch incase of invalid parse
                try:
                    return Value(Type.INT, int(value.v))
                except ValueError:
                    super().error(ErrorType.TYPE_ERROR, "string cannot be converted into integer")
            else:
                super().error(ErrorType.TYPE_ERROR, "brewin objects cannot be converted into integers")

        elif to_type == "str":
            if value.t == Type.STRING:
                return value
            elif value.t == Type.INT:
                return Value(Type.STRING, str(value.v))
            elif value.t == Type.BOOL:
                return Value(Type.STRING, "true" if value.v else "false")
            else:
                super().error(ErrorType.TYPE_ERROR, "brewin objects cannot be converted into strings")

        elif to_type == "bool":
            if value.t == Type.BOOL:
                return value
            elif value.t == Type.INT:
                return Value(Type.BOOL, False if value.v == 0 else True)
            elif value.t == Type.STRING:
                return Value(Type.BOOL, False if value.v == "" else True)
            else:
                super().error(ErrorType.TYPE_ERROR, "brewin objects cannot be converted into bools")
        
        else:
            super().error(ErrorType.TYPE_ERROR, "invalid conversion")


    def __assign_dotted(self, var_name, expr):
        """
        Writing to a field must check all intermediate segments must 
        have been assigned to a valid object and be o-typed    
        """
        parts = var_name.split('.')
        value = self.__eval_expr(expr)

        # check validity from [root, final) field
        if not self.env.exists(parts[0]):
            super().error(ErrorType.NAME_ERROR, f"Object {parts[0]} not defined")
        
        curr = self.env.get(parts[0])
        for p in parts[1:-1]:
            if curr.t != Type.OBJECT:
                super().error(ErrorType.TYPE_ERROR, "cannot access member on non-objects")
            if curr.v is None:
                super().error(ErrorType.FAULT_ERROR, "Accessing non-object type or dereferncing a nil object")
            if not curr.v.has_field(p):
                super().error(ErrorType.NAME_ERROR, "Field does not exist")

            curr = curr.v.get_field(p)
        if curr.t != Type.OBJECT:
            super().error(ErrorType.TYPE_ERROR, "Cannot set field on non-member object")
        if curr.v is None:
            super().error(ErrorType.FAULT_ERROR, "Cannot set field on nil object")

        # do assignment and type check
        final = parts[-1]
        type = self.__get_type_from_suffix(final)
        self.__validate_type(type, value)
        
        curr.v.set_field(final, value)

    def __eval_dotted_names(self, var_name):
        parts = var_name.split('.')

        # check validity from [root, final] field
        if not self.env.exists(parts[0]):
            super().error(ErrorType.NAME_ERROR, f"Object {parts[0]} not defined")
        
        curr = self.env.get(parts[0])
        for p in parts[1:]:
            if curr.t != Type.OBJECT:
                super().error(ErrorType.TYPE_ERROR, "Cannot access non-object type")
            if curr.v is None:
                super().error(ErrorType.FAULT_ERROR, "Accessing non-object type or dereferncing a nil object")
            if not curr.v.has_field(p):
                super().error(ErrorType.NAME_ERROR, "Field does not exist")

            curr = curr.v.get_field(p)
    
        return curr

        

def main():
    interpreter = Interpreter()

    test_overloaded_func = """
    def getValuei() {
        return 100;
    }

    def getValuei(ai) {
        return ai + 50;
    }

    def main() {
    var resulti;
    
    resulti = getValuei();
    print(resulti);
    
    resulti = getValuei(25);
    print(resulti);
    }
    """
    test_overloaded_default_func = """ 
    def getValuei() {
        return;
    }

    def getValuei(ai) {
        return ai + 50;
    }

    def main() {
    var resulti;
    
    resulti = getValuei();
    print(resulti);
    
    resulti = getValuei(25);
    print(resulti);
    }
    """

    test_early_exit = """ 
    def getValuei() {
        return;
    }

    def getValuei(ai) {
        return ai + 50;
    }

    def main() {
    var resulti;
    
    resulti = getValuei();
    print(resulti);
    
    return resulti; 

    resulti = getValuei(25);
    print(resulti);
    }
    """

    test_paramter_no_type = """ 
    def getValuei(a) {
        return ai + 50;
    }

    def main() {
    var resulti;
    
    resulti = getValuei();
    print(resulti);

    return; 
    }
    """

    test_int_conversion = """
    def main() {
        var bs;
        bs = "this shouldn't work";
        var ci;
        ci = int(bs);
        print(ci);
    }
    """

    test_str_conversion = """
    def main() {
        var bi;
        bi = 67;
        var cs;
        cs = str(bi);
        print(cs);
    }    
    """
    test_bool_conversion = """
    def main() {
        var bs;
        bs = "this should output true";
        var cb;
        cb = bool(bs);
        print(cb);
    }    
    """

    test_pass_by_ref = """
    def modify_by_valuev(xi) 
    {
        xi = 999;
    } /* no effect on caller */
    
    def modify_by_refv(&xi) 
    { 
        xi = 888; 
    } /* changes caller's testi */

    def main() {
        var testi; 
        testi = 42;
        modify_by_valuev(testi);
        print(testi);         /* 42 */
        modify_by_refv(testi);
        print(testi);         /* 888 */
    }
    """

    test_objects = """
    def main() {
        var uo; 
        uo = @;
        var ao; 
        ao = @;
        uo.addresso = ao;
        uo.addresso.zipi = 90024;
        print(uo.addresso.zipi);  /* 90024 */
    }
    """

    program = """
    def main() {
        var ci;
        if (true) {
            bvar ci;     /* name error: variable already defined! */
        }
    }
    """

    # should print 100
    test_pass_by_ref = """
    def modifyv(&xi) {
        xi = 100;
    }

    def modiffyv(xi) {
        xi = 100;
    }

    def main() {
        var testi;
        testi = 42;
        modiffyv(testi);
        print(testi);
        modifyv(testi);
        print(testi);
    }
    """

    program = """
    def main() {
        print("Starting test");
        foov(1);
    }

    def foov(param1v) {
        print("This function has a formal parameter with void type");
    }
    """

    test_void_var = """
    def main() {
        var xv;
    }
    """

    program = """
def main() {
    var objo;
    objo = @;
    objo.xi = 5;
    objo.xi.yi = 10;
}

    """

    # # To test your own Brewin program, place it in `test.br` and run this main function.
    # with open("./v3/tests/test_function_overloading_expression.br", "r") as f:
    #     program = f.read()

    interpreter.run(program)


if __name__ == "__main__":
    main()