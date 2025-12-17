from intbase import InterpreterBase, ErrorType
from brewparse import parse_program
from element import Element
from copy import copy, deepcopy
import enum

from debug_utils import debug_logger, debug_logger_with_return_val, debug, info


class Type(enum.Enum):
    INT = 1
    STRING = 2
    BOOL = 3
    OBJECT = 4
    VOID = 5
    FUNCTION = 6
    ERROR = 7

    @staticmethod
    def get_type(var_name):
        if not var_name:
            return Type.ERROR
        last_letter = var_name[-1]
        if last_letter == "i":
            return Type.INT
        if last_letter == "s":
            return Type.STRING
        if last_letter == "b":
            return Type.BOOL
        if last_letter == "o":
            return Type.OBJECT
        if last_letter == "v":
            return Type.VOID  # only for functions
        if last_letter == "f":
            return Type.FUNCTION
        if last_letter.isupper():
            return Type.OBJECT # treat interfaces as objects at runtime
        return Type.ERROR


class Value:
    def __init__(self, t, v=None):
        if v is None:
            self.t = t
            self.v = self.__default_value_for_type(t)
        else:
            self.t = t
            self.v = v

    def set(self, other):
        self.t = other.t
        self.v = other.v

    def __default_value_for_type(self, t):
        if t == Type.INT:
            return 0
        if t == Type.STRING:
            return ""
        elif t == Type.BOOL:
            return False
        elif t == Type.OBJECT:
            return (
                None  # representing Nil as an object type value with None as its value
            )
        elif t == Type.FUNCTION:
            return None # representing Nil
        elif t == Type.VOID:
            return None

        raise Exception("invalid default value for type")


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
    def fdef(self, varname, value):
        top_env = self.env[-1]
        # differentiate from block scope
        if varname in top_env[0]:
            return False
        top_env[0][varname] = value
        return True

    # define new variable in top block
    def bdef(self, varname, value):
        # allow shadowing in block scope
        top_env = self.env[-1]
        if varname in top_env[-1]:
            return False        
        top_env[-1][varname] = value
        return True

    def exists(self, varname):
        for block in self.env[-1]:
            if varname in block:
                return True
        return False

    def get(self, varname):
        top_env = self.env[-1]
        for block in reversed(top_env):
            if varname in block:
                return block[varname]
        return None

    def set(self, varname, value):
        if not self.exists(varname):
            return False
        top_env = self.env[-1]
        for block in reversed(top_env):
            if varname in block:
                block[varname] = value
                return True
        return False
    
    def capture_vars(self):
        """Capture all variables in scope for lambda implementation"""
        captured = {}
        for block in self.env[-1]:
            for name, val in block.items():
                captured[name] = val
        return captured

class Function:
    def __init__(self, func_ast):
        self.return_type = self.__get_return_type(func_ast)
        # the args in the ast is a list of qualified name nodes
        self.formal_args = {a.get("name"): a.get("ref") for a in func_ast.get("args")}
        self.statements = func_ast.get("statements")

    def __get_return_type(self, func_ast):
        name = func_ast.get("name")
        if name == "main":
            return Type.VOID

        return Type.get_type(name)


# Inherits from Function with added captured variables
class Lambda(Function):
    def __init__(self, lambda_ast, captured_vars):
        super().__init__(lambda_ast)
        self.captured_vars = captured_vars


class Interface:
    def __init__(self, name, fields):
        self.name = name
        self.field_vars = {}
        self.field_funcs = {}

        self.__assign_fields(fields)

    # @debug_logger_with_return_val
    def __assign_fields(self, fields):
        for field in fields:
            if field.elem_type == InterpreterBase.FIELD_VAR_NODE:
                var_name = field.get("name")
                var_type = Type.get_type(var_name)
                self.field_vars[var_name] = var_type

            elif field.elem_type == InterpreterBase.FIELD_FUNC_NODE:
                func_name = field.get("name")
                params = field.get("params")
                param_sig = []
                for p in params:
                    p_name = p.get("name")
                    p_type = Type.get_type(p_name)
                    p_ref = p.get("ref")
                    param_sig.append((p_type, p_ref))
                self.field_funcs[func_name] = param_sig


class Interpreter(InterpreterBase):
    def __init__(self, console_output=True, inp=None, trace_output=False):
        super().__init__(console_output, inp)
        self.funcs = {}
        self.interfaces = {}
        self.env = Environment()
        self.bops = {"+", "-", "*", "/", "==", "!=", ">", ">=", "<", "<=", "||", "&&"}

    def run(self, program):
        ast = parse_program(program, plot=False)
        self.__create_interface_table(ast)
        self.__create_function_table(ast)
        call_element = Element(InterpreterBase.FCALL_NODE, name="main", args=[])
        self.__run_fcall(call_element)

    def __get_parameters_type_signature(self, formal_params):
        # a formal arg is an Element of type ARG_NODE
        param_type_sig = ""
        for p in formal_params:
            p_last = p.get("name")[-1]
            # handle interface -> object type
            if p_last.isupper():
                param_type_sig += 'o'
            else:
                param_type_sig += p_last
        allowed = "biosf"
        if not all(c in allowed for c in param_type_sig):
            super().error(ErrorType.TYPE_ERROR, "invalid type in formal parameter")
        return param_type_sig

    # @debug_logger_with_return_val
    def __get_arguments_type_signature(self, actual_args):
        arg_sig = ""
        for arg in actual_args:
            if arg.t == Type.INT:
                arg_sig += "i"
            elif arg.t == Type.STRING:
                arg_sig += "s"
            elif arg.t == Type.BOOL:
                arg_sig += "b"
            elif arg.t == Type.OBJECT:
                arg_sig += "o"
            elif arg.t == Type.FUNCTION:
                arg_sig += "f"
            elif arg.t == Type.VOID:
                super().error(
                    ErrorType.TYPE_ERROR, "void type not allowed as parameter"
                )
            else:
                raise Exception("shouldn't reach this!")
        return arg_sig

    # @debug_logger_with_return_val
    def __create_interface_table(self, ast):
        self.interfaces = {}
        interfaces = ast.get("interfaces")
        if interfaces is None:
            return
         
        for interface in interfaces:
            name = interface.get("name")

            # name must be an uppercase letter
            if len(name) != 1 or not name.isupper():
                super().error(ErrorType.NAME_ERROR, "interface name must be an uppercase letter")
            if name in self.interfaces:
                super().error(ErrorType.NAME_ERROR, "interface already defined")
            
            fields = interface.get("fields")

            # check for duplicate field names
            defined_fields = set()
            for field in fields:
                field_name = field.get("name")
                if field_name in defined_fields:
                    super().error(ErrorType.NAME_ERROR, "duplicate field names in interfaces are not allowed")
                defined_fields.add(field_name)

            self.interfaces[name] = Interface(name, fields)

    def __get_interface_name(self, name):
        if not name:
            return None
        if name[-1].isupper():
            return name[-1]
        return None  # not an interface

    # @debug_logger_with_return_val
    def __interface_satisfaction(self, obj, interface_name):
        if interface_name not in self.interfaces:
            super().error(ErrorType.NAME_ERROR, "interface does not exist")
        
        interface = self.interfaces[interface_name]

        # project spec: may assign/pass nil to an interface variable/parameter.
        if obj.v is None:
            return True
        
        # we only expect object types
        if obj.t != Type.OBJECT:
            return False
        
        # compare object fields to named fields and functions of interface
        obj_fields = obj.v

        for field_name, field_type in interface.field_vars.items():
            if field_name not in obj_fields:
                return False
            obj_value = obj_fields[field_name]
            if obj_value.t != field_type:
                return False
            
        for field_name, field_sig in interface.field_funcs.items():
            if field_name not in obj_fields:
                return False
            obj_value = obj_fields[field_name]

            if obj_value.t != Type.FUNCTION:
                return False

            # check if function signatures match
            if not self.__check_function_signatures(obj_value.v, field_sig):
                return False
        return True

    # @debug_logger_with_return_val
    def __check_function_signatures(self, obj_sig, field_sig):
        # object signatures should match. Count, types, and if reference
        formal_args = obj_sig.formal_args

        if len(formal_args) != len(field_sig):
            return False
        
        for formal_name, (field_type, field_ref) in zip(formal_args.keys(), field_sig):
            formal_type = Type.get_type(formal_name)

            if formal_type != field_type:
                return False
            
            formal_ref = formal_args[formal_name]
            if formal_ref != field_ref:
                return False
        return True
    
    # @debug_logger_with_return_val
    def __create_lambda(self, lambda_ast):
        inscope_vars = self.env.capture_vars()
        lambda_params = lambda_ast.get("args")

        # create closure with correct capture methods
        # primitives -> capture by value. objs and funcs -> capture by ref
        captured_vars = {}
        for name, val in inscope_vars.items():
            # shadow if lambda parameters with same name as captured variables
            if name in lambda_params:
                continue

            if val.t in {Type.INT, Type.STRING, Type.BOOL}:
                captured_vars[name] = copy(val)
            elif val.t in {Type.OBJECT, Type.FUNCTION}:
                captured_vars[name] = Value(val.t, val.v) # prevent global reassignment
            else:
                captured_vars[name] = copy(val)

        lambda_obj = Lambda(lambda_ast, captured_vars)
        return Value(Type.FUNCTION, lambda_obj)
        
   
    # @debug_logger_with_return_val
    def __create_function_table(self, ast):
        self.funcs = {}
        valid_types = {"i", "s", "b", "o", "f"}
        for func in ast.get("functions"):
            name = func.get("name")
            param_type_sig = self.__get_parameters_type_signature(func.get("args"))
            func_obj = Function(func)
            if func_obj.return_type == Type.ERROR:
                super().error(ErrorType.TYPE_ERROR)
            type_sig = (name, param_type_sig)
            if type_sig in self.funcs:
                super().error(ErrorType.NAME_ERROR, "function already defined")
            self.funcs[type_sig] = func_obj

    # @debug_logger_with_return_val
    def __get_function(self, name, param_type_signature=""):
        if (name, param_type_signature) not in self.funcs:
            super().error(ErrorType.NAME_ERROR, "function not found")
        return self.funcs[(name, param_type_signature)]

    def __run_vardef(self, statement, block_def=False):
        name = statement.get("name")
        var_type = Type.get_type(name)
        if var_type == Type.ERROR or var_type == Type.VOID:
            super().error(ErrorType.TYPE_ERROR, "invalid variable type")

        default_value = Value(var_type)
        if block_def:
            if not self.env.bdef(name, default_value):
                super().error(ErrorType.NAME_ERROR, "variable already defined")
        else:
            if not self.env.fdef(name, default_value):
                super().error(ErrorType.NAME_ERROR, "variable already defined")

    # @debug_logger_with_return_val
    def __run_assign(self, statement):
        name = statement.get("var")
        dotted_name = name.split(".")
        rvalue = self.eval_expr(statement.get("expression"))

        if not self.env.exists(dotted_name[0]):
            super().error(ErrorType.NAME_ERROR, "variable not defined")

        var_type = Type.get_type(dotted_name[-1])

        # check if assignment to interface: returns either the name or None
        interface_name = self.__get_interface_name(dotted_name[-1])
        if interface_name:
            if rvalue.t != Type.OBJECT:
                super().error(ErrorType.TYPE_ERROR, "interface variable can only be assigned to an object")
            # check if the obj value satisfies the interface
            elif not self.__interface_satisfaction(rvalue, interface_name):
                super().error(ErrorType.TYPE_ERROR, "object does not satisfy the interface")
        else:
            # allow nil assignment to objects and function
            if rvalue.v is None:
                if var_type not in [Type.OBJECT, Type.FUNCTION]:
                    super().error(ErrorType.TYPE_ERROR, "type mismatch in assignment")

            elif var_type != rvalue.t:
                super().error(ErrorType.TYPE_ERROR, "type mismatch in assignment")

        if len(dotted_name) == 1:
            value = self.env.get(name)
            value.set(
                rvalue
            )  # update the value pointed to by the variable, not the mapping in the env
            return

        lvalue = self.env.get(dotted_name[0])
        if lvalue.t != Type.OBJECT:
            super().error(ErrorType.TYPE_ERROR, "cannot access member of non-object")
        if lvalue.v == None:
            super().error(ErrorType.FAULT_ERROR, "cannot dereference nil object")

        suffix_name = dotted_name[1:-1]
        # xo.yo.zi = 5;
        for sub in suffix_name:
            if sub not in lvalue.v:
                super().error(ErrorType.NAME_ERROR, "object member not found")
            # every inner item must be an object, ending in an o
            if sub[-1] != "o" and not sub[-1].isupper():
                super().error(ErrorType.TYPE_ERROR, "member must be an object")
            lvalue = lvalue.v[sub]
            # every inner object must be non-nil
            if lvalue.v == None:
                super().error(
                    ErrorType.FAULT_ERROR, "cannot dereference nil member object"
                )

        if rvalue.t == Type.OBJECT:
            lvalue.v[dotted_name[-1]] = rvalue
        else:
            lvalue.v[dotted_name[-1]] = Value(rvalue.t, rvalue.v)

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
            c_out = self.eval_expr(arg)
            if c_out.t == Type.VOID:
                super().error(
                    ErrorType.TYPE_ERROR, "cannot pass void argument to function"
                )
            if c_out.t == Type.BOOL:
                out += str(c_out.v).lower()
            else:
                out += str(c_out.v)

        super().output(out)

        return Value(Type.VOID, None)

    # @debug_logger_with_return_val
    def __run_fcall(self, func_call_ast):
        fcall_name, args = func_call_ast.get("name"), func_call_ast.get("args")

        if fcall_name == "inputi" or fcall_name == "inputs":
            return self.__handle_input(fcall_name, args)

        if fcall_name == "print":
            return self.__handle_print(args)

        # call through method, if it is one
        if "." in fcall_name:
            return self.__run_method_call(fcall_name, args)

        # call through function value, if it is one
        if self.env.env: # make sure we're at least in main
            func_val = self.env.get(fcall_name)
            if func_val is not None and func_val.t == Type.FUNCTION:
                if func_val.v is None:
                    super().error(ErrorType.FAULT_ERROR, "cannot call a nil function")
                # helper function for calling through function value
                return self.__call_function_value(func_val.v, args)

        actual_args = [self.eval_expr(a) for a in args]
        args_type_sig = self.__get_arguments_type_signature(actual_args)

        # check bad interface parameter passing. 
        # when func_def fails, it will always give name error. In the case above, we need to check for Type.ERROR too
        try:
            func_def = self.__get_function(fcall_name, args_type_sig)
        except:
            # name error means there could be a function that exists but wrong type signatures
            existing_funcs = []
            for key in self.funcs.keys():
                if key[0] == fcall_name:
                    existing_funcs.append(self.funcs[key])
            if existing_funcs:
                super().error(ErrorType.TYPE_ERROR, "argument type mismatch")
            else:
                super().error(ErrorType.NAME_ERROR, "function not found")
                
        # interface satisfaction during parameter passing
        for formal_name, actual_arg in zip(func_def.formal_args.keys(), actual_args):
            interface_name = self.__get_interface_name(formal_name) # return interface name or None
            if interface_name:
                if actual_arg.t != Type.OBJECT:
                    super().error(ErrorType.TYPE_ERROR, "argument can only be an object")
                # check if the obj value satisfies the interface
                elif not self.__interface_satisfaction(actual_arg, interface_name):
                    super().error(ErrorType.TYPE_ERROR, "argument does not satisfy the interface")

        self.env.enter_func()
        for formal, actual in zip(func_def.formal_args.keys(), actual_args):
            ref_param = func_def.formal_args[
                formal
            ]  # determine if it's a reference or not
            actual = self.__clone_for_passing(actual, ref_param)
            self.env.fdef(
                formal, actual
            )  # no need to check types since we used types for overloading to pick a compatible function already
        res, _ = self.__run_statements(func_def, func_def.statements)
        self.env.exit_func()

        return res
    
    # @debug_logger_with_return_val
    def __run_method_call(self, method_path, args):
        dotted_name = method_path.split(".")
        
        if not self.env.exists(dotted_name[0]):
            super().error(ErrorType.NAME_ERROR, "variable not defined")
        
        value = self.env.get(dotted_name[0])
        suffix_name = dotted_name[1:]
        for i, sub in enumerate(suffix_name[:-1]):
            if value.v == None:  # NIL
                super().error(ErrorType.FAULT_ERROR, "nil reference access")
            if sub not in value.v:
                super().error(ErrorType.NAME_ERROR, "object member not found")
            # every inner item must be an object, ending in an o        
            if i < len(suffix_name) - 1 and sub[-1] != "o":
                super().error(ErrorType.TYPE_ERROR, "member must be an object")
            value = value.v[sub]

        method_name = suffix_name[-1]
        # make sure object has the method
        if method_name not in value.v:
            super().error(ErrorType.NAME_ERROR, "method not found")
        method_value = value.v[method_name]

        # check if valid function
        if method_value.t != Type.FUNCTION:
            super().error(ErrorType.TYPE_ERROR, "calling a non-function")
        if method_value.v is None:
            super().error(ErrorType.FAULT_ERROR, "calling a nil function")

        return self.__call_function_value(method_value.v, args, value)

    def __call_function_value(self, func_obj, args, selfo=None):
        actual_args = [self.eval_expr(a) for a in args]
        args_type_sig = self.__get_arguments_type_signature(actual_args)

        # validate number of arguments and types
        if len(actual_args) != len(func_obj.formal_args):
            super().error(ErrorType.TYPE_ERROR, "number of arguments don't match")
        
        for formal, actual in zip(func_obj.formal_args.keys(), actual_args):
            corr_type = Type.get_type(formal)
            if corr_type != actual.t:
                super().error(ErrorType.TYPE_ERROR, "argument type mismatch")

            # check interface is satisfied when passed through function value
            interface_name = self.__get_interface_name(formal)
            if interface_name:
                if actual.t != Type.OBJECT:
                    super().error(ErrorType.TYPE_ERROR, "argument takes in object of interface type")
                if not self.__interface_satisfaction(actual, interface_name):
                    super().error(ErrorType.TYPE_ERROR, "object does not satisfy interface")
        self.env.enter_func()

        # if method call, define selfo too
        if selfo is not None:
            self.env.fdef("selfo", selfo)

        # if lambda, define the captured variable too
        if isinstance(func_obj, Lambda):
            for name, val in func_obj.captured_vars.items():
                self.env.fdef(name, val)

        for formal, actual in zip(func_obj.formal_args.keys(), actual_args):
            ref_param = func_obj.formal_args[
                formal
            ]  # determine if it's a reference or not
            actual = self.__clone_for_passing(actual, ref_param)
            
            # handle shadowing if parameter shadows variable
            if self.env.exists(formal):
                shadowed_val = self.env.get(formal)
                shadowed_val.set(actual)
            else:
                self.env.fdef(
                    formal, actual
                )  # no need to check types since we used types for overloading to pick a compatible function already
        res, _ = self.__run_statements(func_obj, func_obj.statements)
        self.env.exit_func()

        return res
    
    def __clone_for_passing(self, arg, ref_param):
        if ref_param:
            return arg  # pass by reference - value is the original value from the calling function
        return copy(
            arg
        )  # perform a shallow copy of the value, but still point at the original Python value

    def __run_if(self, funcdef, statement):
        cond = self.eval_expr(statement.get("condition"))

        if cond.t != Type.BOOL:
            super().error(ErrorType.TYPE_ERROR, "condition must be boolean")

        self.env.enter_block()

        res, ret = Value(funcdef.return_type), False

        if cond.v:
            res, ret = self.__run_statements(funcdef, statement.get("statements"))
        elif statement.get("else_statements"):
            res, ret = self.__run_statements(funcdef, statement.get("else_statements"))

        self.env.exit_block()

        return res, ret

    def __run_while(self, funcdef, statement):
        res, ret = Value(funcdef.return_type), False

        while True:
            cond = self.eval_expr(statement.get("condition"))

            if cond.t != Type.BOOL:
                super().error(ErrorType.TYPE_ERROR, "condition must be boolean")

            if not cond.v:
                break

            self.env.enter_block()
            res, ret = self.__run_statements(funcdef, statement.get("statements"))
            self.env.exit_block()
            if ret:
                break

        return res, ret

    def __run_return(self, funcdef, statement):
        expr = statement.get("expression")
        if not expr:
            return (Value(funcdef.return_type), True)
        result_val = self.eval_expr(expr)
        if result_val.t != funcdef.return_type:
            super().error(ErrorType.TYPE_ERROR, "return type mismatch")
        return (result_val, True)

    def __run_statements(self, funcdef, statements):
        res, ret = Value(funcdef.return_type), False

        for statement in statements:
            kind = statement.elem_type

            if kind == self.VAR_DEF_NODE:
                self.__run_vardef(statement)
            if kind == self.BVAR_DEF_NODE:
                self.__run_vardef(statement, True)
            elif kind == "=":
                self.__run_assign(statement)
            elif kind == self.FCALL_NODE:
                self.__run_fcall(statement)
            elif kind == self.IF_NODE:
                res, ret = self.__run_if(funcdef, statement)
                if ret:
                    break
            elif kind == self.WHILE_NODE:
                res, ret = self.__run_while(funcdef, statement)
                if ret:
                    break
            elif kind == self.RETURN_NODE:
                res, ret = self.__run_return(funcdef, statement)
                break

        return res, ret

    def __eval_binary_op(self, kind, vl, vr):
        """Evaluate binary operations"""
        tl, tr = vl.t, vr.t
        vl_val, vr_val = vl.v, vr.v

        if kind == "==":
            # nil == nil always true
            if vl_val is None and vr_val is None:
                return Value(Type.BOOL, True)

            if tl == Type.OBJECT and tr == Type.OBJECT:
                return Value(Type.BOOL, tl == tr and vl_val is vr_val)

            # function-variables equality
            if tl == Type.FUNCTION and tr == Type.FUNCTION:
                return Value(Type.BOOL, tl == tr and vl_val is vr_val)

            # function and nil comparison
            if (tl == Type.FUNCTION and tr == Type.OBJECT):
                return Value(Type.BOOL, False)    
                
            return Value(Type.BOOL, tl == tr and vl_val == vr_val)
        
        if kind == "!=":
            if vl_val is None and vr_val is None:
                return Value(Type.BOOL, False)

            if tl == Type.OBJECT and tr == Type.OBJECT:
                return Value(Type.BOOL, not (tl == tr and vl_val is vr_val))
            
            if tl == Type.FUNCTION and tr == Type.FUNCTION:
                return Value(Type.BOOL, not (tl == tr and vl_val is vr_val))

            if (tl == Type.FUNCTION and tr == Type.OBJECT):
                return Value(Type.BOOL, True)  
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

    def __eval_convert(self, expr):
        """Evaluate type conversion operations"""
        val = self.eval_expr(expr.get("expr"))
        to_type = expr.get("to_type")

        if to_type == "int":
            if val.t == Type.INT:
                return val
            elif val.t == Type.STRING:
                try:
                    return Value(Type.INT, int(val.v))
                except ValueError:
                    super().error(ErrorType.TYPE_ERROR, "cannot convert string to int")
            elif val.t == Type.BOOL:
                return Value(Type.INT, 1 if val.v else 0)
            else:
                super().error(ErrorType.TYPE_ERROR, "cannot convert object to int")

        elif to_type == "str":
            if val.t == Type.STRING:
                return val
            elif val.t == Type.INT:
                return Value(Type.STRING, str(val.v))
            elif val.t == Type.BOOL:
                return Value(Type.STRING, str(val.v).lower())
            else:
                super().error(ErrorType.TYPE_ERROR, "cannot convert object to string")

        elif to_type == "bool":
            if val.t == Type.BOOL:
                return val
            elif val.t == Type.INT:
                return Value(Type.BOOL, val.v != 0)
            elif val.t == Type.STRING:
                return Value(Type.BOOL, val.v != "")
            else:
                super().error(ErrorType.TYPE_ERROR, "cannot convert object to bool")
        else:
            super().error(ErrorType.TYPE_ERROR, "invalid conversion type")

    # @debug_logger_with_return_val
    def __get_var_value(self, expr):
        dotted_name = expr.get("name").split(".")

        # first-class functions: check if defined function, not variable
        if len(dotted_name) == 1:
            func_name = dotted_name[0]

            # look for matching functions, by function signature
            func_var = [key for key in self.funcs.keys() if key[0] == func_name]

            if len(func_var) == 1:
                func_obj = self.funcs[func_var[0]]
                return Value(Type.FUNCTION, func_obj)
            # ambiguous case: undefined behavior
            elif len(func_var) > 1:
                super().error(ErrorType.NAME_ERROR, "ambiguous function-value assignments for overloaded names")

        if not self.env.exists(dotted_name[0]):
            super().error(ErrorType.NAME_ERROR, "variable not defined")
        value = self.env.get(dotted_name[0])
        suffix_name = dotted_name[1:]

        # handle interface base types too
        if len(dotted_name) > 1:
            base_last_ltr = dotted_name[0][-1]
            if not base_last_ltr.isupper() and base_last_ltr != "o":
                super().error(ErrorType.TYPE_ERROR, "cannot dereference a non-object")
        for i, sub in enumerate(suffix_name):
            if value.v == None:  # NIL
                super().error(ErrorType.FAULT_ERROR, "nil reference access")
            if sub not in value.v:
                super().error(ErrorType.NAME_ERROR, "object member not found")
            # every inner item must be an object, ending in an o
            if i < len(suffix_name) - 1 and sub[-1] != "o" and not sub[-1].isupper():
                super().error(ErrorType.TYPE_ERROR, "member must be an object")
            value = value.v[sub]
        return value

    # @debug_logger_with_return_val
    def eval_expr(self, expr):
        kind = expr.elem_type

        if kind == self.INT_NODE:
            return Value(Type.INT, expr.get("val"))

        if kind == self.STRING_NODE:
            return Value(Type.STRING, expr.get("val"))

        if kind == self.BOOL_NODE:
            return Value(Type.BOOL, expr.get("val"))

        if kind == self.NIL_NODE:
            return Value(Type.OBJECT)

        if kind == self.EMPTY_OBJ_NODE:
            return Value(Type.OBJECT, {})

        if kind == self.QUALIFIED_NAME_NODE:
            return self.__get_var_value(expr)

        if kind == self.FCALL_NODE:
            return self.__run_fcall(expr)

        if kind == self.FUNC_NODE: # lambda
            return self.__create_lambda(expr)

        if kind in self.bops:
            l, r = self.eval_expr(expr.get("op1")), self.eval_expr(expr.get("op2"))
            return self.__eval_binary_op(kind, l, r)

        if kind == self.NEG_NODE:
            o = self.eval_expr(expr.get("op1"))
            if o.t == Type.INT:
                return Value(Type.INT, -o.v)

            super().error(ErrorType.TYPE_ERROR, "cannot negate non-integer")

        if kind == self.NOT_NODE:
            o = self.eval_expr(expr.get("op1"))
            if o.t == Type.BOOL:
                return Value(Type.BOOL, not o.v)

            super().error(ErrorType.TYPE_ERROR, "cannot apply NOT to non-boolean")

        if kind == self.CONVERT_NODE:
            return self.__eval_convert(expr)

        raise Exception("should not get here!")


def main():
    import sys

    interpreter = Interpreter()

    # Use command line argument if provided, otherwise default to test.br
    filename = sys.argv[1] if len(sys.argv) > 1 else "./test.br"

    with open(filename, "r") as f:
        program = f.read()

    interpreter.run(program)


if __name__ == "__main__":
    main()