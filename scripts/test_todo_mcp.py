import asyncio
import json
from mcp.client.stdio import stdio_client, StdioServerParameters
from mcp import ClientSession

SERVER_SCRIPT = "practices/practice_04/my_mcp/todo_mcp_server.py"

async def main():
    server_params = StdioServerParameters(command=".venv/bin/python", args=[SERVER_SCRIPT])

    results = {}

    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:
            # wait until server registers tools
            for i in range(10):
                try:
                    tools = list(session.tools.keys())
                    if tools:
                        break
                except Exception:
                    pass
                await asyncio.sleep(0.1)

            # 1. list_tasks (no arguments)
            try:
                res1 = await session.call_tool("list_tasks", {})
            except Exception as e:
                results['list_tasks_before_error'] = str(e)
                res1 = []
            results['list_tasks_before'] = res1

            # 2. add_task
            add_args = {"title": "Test MCP", "description": "Verify todo-mcp works correctly"}
            try:
                res2 = await session.call_tool("add_task", add_args)
            except Exception as e:
                results['add_task_error'] = str(e)
                res2 = None
            results['add_task'] = res2

            # 3. list_tasks after add
            try:
                res3 = await session.call_tool("list_tasks", {})
            except Exception as e:
                results['list_tasks_after_add_error'] = str(e)
                res3 = []
            results['list_tasks_after_add'] = res3

            # 4. search_tasks
            try:
                res4 = await session.call_tool("search_tasks", {"query": "Test"})
            except Exception as e:
                results['search_tasks_error'] = str(e)
                res4 = []
            results['search_tasks'] = res4

            # 5. complete_task
            created = None
            if isinstance(res2, dict) and 'id' in res2:
                created = res2['id']
            else:
                try:
                    created = getattr(res2, 'id', None) or (res2.get('id') if isinstance(res2, dict) else None)
                except Exception:
                    created = None

            if created is None:
                for t in reversed(results.get('list_tasks_after_add', [])):
                    if t.get('title') == 'Test MCP':
                        created = t.get('id')
                        break

            results['created_task_id'] = created

            if created is None:
                results['complete_task'] = {"error": "could not determine created task id"}
            else:
                try:
                    res5 = await session.call_tool("complete_task", {"task_id": created})
                except Exception as e:
                    results['complete_task_error'] = str(e)
                    res5 = None
                results['complete_task'] = res5

                # 6. final list
                try:
                    res6 = await session.call_tool("list_tasks", {})
                except Exception as e:
                    results['list_tasks_final_error'] = str(e)
                    res6 = []
                results['list_tasks_final'] = res6

    # Simplify to JSON-serializable
    def simplify(obj):
        try:
            return json.loads(json.dumps(obj))
        except Exception:
            try:
                if hasattr(obj, '__dict__'):
                    return simplify(obj.__dict__)
            except Exception:
                return str(obj)
            return str(obj)

    serializable = {k: simplify(v) for k, v in results.items()}
    print(json.dumps(serializable, ensure_ascii=False, indent=2))

if __name__ == '__main__':
    asyncio.run(main())
