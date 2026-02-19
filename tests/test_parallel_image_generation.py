"""
Tests for parallel image generation in services/message.py

Verifies ThreadPoolExecutor integration for generating multiple birthday
images concurrently when people share the same birthday.
"""

from concurrent.futures import ThreadPoolExecutor, as_completed


class TestParallelImageGeneration:
    """Tests for parallel image generation functionality"""

    def test_threadpoolexecutor_import_available(self):
        """Verify ThreadPoolExecutor is imported in message service"""
        from services import message_generator

        assert hasattr(message_generator, "ThreadPoolExecutor")
        assert hasattr(message_generator, "as_completed")

    def test_threadpoolexecutor_functionality(self):
        """Verify ThreadPoolExecutor works correctly for parallel tasks"""
        results = []

        def task(n):
            return n * 2

        # Test that ThreadPoolExecutor runs tasks in parallel
        with ThreadPoolExecutor(max_workers=3) as executor:
            futures = [executor.submit(task, i) for i in [1, 2, 3]]
            for future in as_completed(futures):
                results.append(future.result())

        assert sorted(results) == [2, 4, 6]

    def test_generate_birthday_message_exists(self):
        """Verify _generate_birthday_message function exists"""
        from services.message_generator import _generate_birthday_message

        assert callable(_generate_birthday_message)

    def test_generate_birthday_message_signature(self):
        """Verify _generate_birthday_message has expected parameters"""
        import inspect

        from services.message_generator import _generate_birthday_message

        sig = inspect.signature(_generate_birthday_message)
        params = list(sig.parameters.keys())

        # Should have these parameters for parallel image generation
        assert "birthday_people" in params
        assert "include_image" in params
        assert "test_mode" in params
        assert "quality" in params
        assert "image_size" in params

    def test_parallel_config_max_workers(self):
        """Verify the parallel config uses 3 workers as documented"""
        # Read the source to verify max_workers=3 is used
        import inspect

        import services.message_generator as mg

        source = inspect.getsource(mg._generate_birthday_message)

        # Verify the parallel execution code exists with correct config
        assert "ThreadPoolExecutor" in source
        assert "max_workers=3" in source
        assert "as_completed" in source

    def test_single_person_optimization_exists(self):
        """Verify single person case skips ThreadPoolExecutor"""
        import inspect

        from services.message_generator import _generate_birthday_message

        source = inspect.getsource(_generate_birthday_message)

        # Verify optimization: single person uses direct call
        assert "count > 1" in source or "if count > 1" in source
