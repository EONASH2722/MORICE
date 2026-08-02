import math
import unittest

from morice.visualization import VisualizationManager


class RenderingAccuracyMatrix(unittest.TestCase):
    """Ten representative renderer cases with independent numeric contracts."""

    def setUp(self):
        self.manager = VisualizationManager()

    def tearDown(self):
        self.manager.shutdown()

    def _render(self, prompt):
        decision = self.manager.decide(prompt)
        self.assertIsNotNone(decision, f"No renderer selected for: {prompt}")
        request = self.manager.create_request(prompt, decision)
        result = self.manager.render(request, lambda *_args: None)
        self.assertTrue(result.ok, result.error)
        self.assertTrue(result.validated)
        self.assertIsNotNone(result.artifact)
        return result.artifact

    def test_01_cubic_landmarks_match_calculus(self):
        artifact = self._render(
            "Plot y=x^3-6*x^2+9*x+2 and mark roots, extrema, and inflection."
        )
        points = {
            point["kind"]: point
            for point in artifact.graph.series[0].inspection_points
        }
        expected = {
            "x-intercept": (-0.195823, 0.0),
            "y-intercept": (0.0, 2.0),
            "maximum": (1.0, 6.0),
            "minimum": (3.0, 2.0),
            "inflection": (2.0, 4.0),
        }
        for kind, (x_value, y_value) in expected.items():
            self.assertIn(kind, points)
            self.assertTrue(
                math.isclose(points[kind]["x"], x_value, abs_tol=0.002)
            )
            self.assertTrue(
                math.isclose(points[kind]["y"], y_value, abs_tol=0.002)
            )

    def test_02_implicit_circle_stays_on_radius_five(self):
        artifact = self._render("Plot the implicit curve x^2+y^2=25.")
        series = artifact.graph.series[0]
        finite = [
            (x_value, y_value)
            for x_value, y_value in zip(series.x, series.y)
            if math.isfinite(x_value) and math.isfinite(y_value)
        ]
        self.assertGreater(len(finite), 100)
        self.assertLess(
            max(abs(math.hypot(x_value, y_value) - 5.0) for x_value, y_value in finite),
            0.003,
        )

    def test_03_polar_cardioid_uses_declared_equation(self):
        artifact = self._render("Plot polar r=2*cos(theta).")
        graph = artifact.graph
        self.assertEqual(
            graph.instruction["parameters"]["coordinateSystem"], "polar"
        )
        series = graph.series[0]
        radii = [
            math.hypot(x_value, y_value)
            for x_value, y_value in zip(series.x, series.y)
        ]
        self.assertTrue(math.isclose(max(radii), 2.0, abs_tol=0.002))
        self.assertLess(min(radii), 0.01)
        self.assertTrue(math.isclose(series.x[0], 2.0, abs_tol=1e-12))
        self.assertTrue(math.isclose(series.y[0], 0.0, abs_tol=1e-12))

    def test_04_parametric_unit_circle_is_unit_radius(self):
        artifact = self._render("Plot parametric x=cos(t), y=sin(t).")
        graph = artifact.graph
        self.assertEqual(
            graph.instruction["parameters"]["coordinateSystem"], "parametric"
        )
        radii = [
            math.hypot(x_value, y_value)
            for x_value, y_value in zip(
                graph.series[0].x, graph.series[0].y
            )
        ]
        self.assertTrue(
            all(math.isclose(radius, 1.0, abs_tol=1e-10) for radius in radii)
        )

    def test_05_paraboloid_surface_matches_x_squared_plus_y_squared(self):
        artifact = self._render("Render 3D z=x^2+y^2.")
        surface = artifact.graph.surface
        self.assertIsNotNone(surface)
        self.assertEqual(
            artifact.graph.instruction["parameters"]["views"], ["2d", "3d"]
        )
        row = len(surface.y) // 2 + 3
        column = len(surface.x) // 2 - 4
        expected = surface.x[column] ** 2 + surface.y[row] ** 2
        self.assertTrue(
            math.isclose(
                surface.z[row][column],
                expected,
                rel_tol=1e-12,
                abs_tol=1e-12,
            )
        )

    def test_06_projectile_uses_requested_forty_five_degree_angle(self):
        artifact = self._render(
            "Simulate projectile motion at 45 degrees with speed 50."
        )
        physics = artifact.physics
        particle = physics.particles[0]
        self.assertEqual(physics.simulation_type, "projectile-2d")
        self.assertTrue(math.isclose(abs(particle.vx), abs(particle.vy), rel_tol=1e-6))
        self.assertGreater(physics.gravity, 0)

    def test_07_pendulum_uses_physical_gravity_and_constraint(self):
        artifact = self._render("Simulate a pendulum released at 30 degrees.")
        physics = artifact.physics
        parameters = physics.instruction["parameters"]
        self.assertEqual(physics.simulation_type, "pendulum-2d")
        self.assertTrue(
            math.isclose(
                parameters["angleRadians"], math.radians(30), rel_tol=1e-12
            )
        )
        self.assertTrue(
            math.isclose(parameters["physicalGravity"], 9.81, rel_tol=1e-12)
        )
        self.assertGreater(parameters["length"], 0)

    def test_08_three_dimensional_particles_have_depth_state(self):
        artifact = self._render(
            "Simulate 120 particles in a 3D box with elastic collisions."
        )
        physics = artifact.physics
        depth = physics.instruction["parameters"]["depth"]
        self.assertEqual(physics.simulation_type, "particle-3d")
        self.assertEqual(len(physics.particles), 120)
        self.assertTrue(
            all(0 < particle.z < depth for particle in physics.particles)
        )
        self.assertTrue(any(abs(particle.vz) > 0 for particle in physics.particles))

    def test_09_sf4_matches_curated_vsepr_geometry(self):
        artifact = self._render("Render an interactive 3D VSEPR model of SF4.")
        molecule = artifact.chemistry
        self.assertEqual(molecule.formula, "SF4")
        self.assertEqual(molecule.geometry, "seesaw")
        self.assertEqual(molecule.electron_geometry, "trigonal bipyramidal")
        self.assertEqual(molecule.central_lone_pairs, 1)
        self.assertEqual(len(molecule.atoms), 5)
        self.assertEqual(len(molecule.bonds), 4)
        self.assertEqual(
            molecule.instruction["parameters"]["views"], ["2d", "3d"]
        )

    def test_10_tcp_handshake_has_expected_directed_sequence(self):
        artifact = self._render("Show the TCP three-way handshake diagram.")
        diagram = artifact.diagram
        self.assertEqual(diagram.title, "TCP three-way handshake")
        self.assertEqual(len(diagram.nodes), 4)
        self.assertEqual(len(diagram.edges), 3)
        node_ids = {node.node_id for node in diagram.nodes}
        self.assertTrue(
            all(
                edge.source in node_ids and edge.target in node_ids
                for edge in diagram.edges
            )
        )

    def test_11_benzene_has_twelve_atoms_and_a_planar_aromatic_ring(self):
        artifact = self._render("Render a complete interactive Benzene molecule.")
        molecule = artifact.chemistry
        self.assertEqual(molecule.formula, "C6H6")
        self.assertEqual(len(molecule.atoms), 12)
        self.assertEqual(len(molecule.bonds), 12)
        self.assertTrue(all(math.isclose(atom.z, 0.0, abs_tol=1e-12) for atom in molecule.atoms))
        self.assertEqual(molecule.instruction["parameters"]["views"], ["2d", "3d"])

    def test_12_mandelbrot_uses_the_escape_time_recurrence(self):
        artifact = self._render("Render an interactive Mandelbrot fractal.")
        surface = artifact.graph.surface
        self.assertEqual(artifact.graph.instruction["simulationType"], "mandelbrot")
        self.assertEqual(artifact.graph.instruction["parameters"]["views"], ["2d", "3d"])
        zero_column = min(range(len(surface.x)), key=lambda index: abs(surface.x[index]))
        zero_row = min(range(len(surface.y)), key=lambda index: abs(surface.y[index]))
        self.assertEqual(surface.z[zero_row][zero_column], 96.0)

    def test_13_lorenz_and_double_pendulum_have_explicit_solver_state(self):
        lorenz = self._render("Render an interactive 3D Lorenz attractor.").physics
        pendulum = self._render("Render a real-time double pendulum simulation.").physics
        self.assertEqual(lorenz.simulation_type, "lorenz-3d")
        self.assertEqual(lorenz.instruction["parameters"]["state"], [0.1, 0.0, 0.0])
        self.assertEqual(lorenz.instruction["parameters"]["views"], ["2d", "3d"])
        self.assertEqual(pendulum.simulation_type, "double-pendulum-2d")
        self.assertEqual(len(pendulum.particles), 2)
        self.assertEqual(len(pendulum.instruction["parameters"]["lengths"]), 2)
        self.assertEqual(pendulum.instruction["parameters"]["views"], ["2d", "3d"])

    def test_14_dashboard_and_maxwell_prompts_do_not_cross_route(self):
        dashboard = self._render(
            "Create a modern scientific dashboard with CPU Usage, GPU Usage, RAM Usage, Current Time, and Current Date."
        )
        maxwell = self._render("Render Maxwell's equations with divergence and curl.")
        self.assertEqual(dashboard.diagram.title, "Scientific system dashboard")
        self.assertEqual(dashboard.diagram.diagram_type, "dashboard")
        self.assertEqual(maxwell.diagram.title, "Maxwell's equations")
        self.assertEqual(len(maxwell.diagram.nodes), 4)


if __name__ == "__main__":
    unittest.main()
