import math
import unittest

from morice.core import wants_model_identity
from morice.domain_engine import build_molecule_artifact
from morice.science_engine import build_science_artifact


class GraphAccuracyTests(unittest.TestCase):
    def test_cubic_landmarks_are_mathematically_correct(self):
        artifact = build_science_artifact(
            "Generate a fully interactive graph of: "
            "y = x^3 - 6x^2 + 9x + 2. "
            "Mark all x-intercepts, y-intercept, local maxima, local minima, and inflection point."
        )

        self.assertIsNotNone(artifact)
        self.assertIsNotNone(artifact.graph)
        points = {point["kind"]: point for point in artifact.graph.series[0].inspection_points}
        expected = {
            "x-intercept": (-0.195823, 0.0),
            "y-intercept": (0.0, 2.0),
            "maximum": (1.0, 6.0),
            "minimum": (3.0, 2.0),
            "inflection": (2.0, 4.0),
        }
        for kind, (expected_x, expected_y) in expected.items():
            self.assertIn(kind, points)
            self.assertTrue(math.isclose(points[kind]["x"], expected_x, abs_tol=0.002))
            self.assertTrue(math.isclose(points[kind]["y"], expected_y, abs_tol=0.002))

    def test_repeated_root_is_detected(self):
        artifact = build_science_artifact("Plot y=(x-1)^2")
        roots = [
            point
            for point in artifact.graph.series[0].inspection_points
            if point["kind"] == "x-intercept"
        ]
        self.assertEqual(len(roots), 1)
        self.assertTrue(math.isclose(roots[0]["x"], 1.0, abs_tol=0.002))

    def test_discontinuity_is_not_reported_as_root(self):
        artifact = build_science_artifact("Plot y=1/x")
        roots = [
            point
            for point in artifact.graph.series[0].inspection_points
            if point["kind"] == "x-intercept"
        ]
        self.assertEqual(roots, [])

    def test_surface_grid_matches_known_paraboloid_samples(self):
        artifact = build_science_artifact("Plot 3D z=x^2+y^2")

        self.assertIsNotNone(artifact)
        self.assertIsNotNone(artifact.graph.surface)
        surface = artifact.graph.surface
        center = len(surface.x) // 2
        self.assertTrue(math.isclose(surface.x[center], 0.0, abs_tol=1e-12))
        self.assertTrue(math.isclose(surface.y[center], 0.0, abs_tol=1e-12))
        self.assertTrue(math.isclose(surface.z[center][center], 0.0, abs_tol=1e-12))
        sample_row = center + 4
        sample_column = center - 3
        expected = surface.x[sample_column] ** 2 + surface.y[sample_row] ** 2
        self.assertTrue(
            math.isclose(
                surface.z[sample_row][sample_column],
                expected,
                rel_tol=1e-10,
                abs_tol=1e-10,
            )
        )
        self.assertTrue(math.isclose(surface.z_range[0], 0.0, abs_tol=1e-12))
        self.assertTrue(math.isclose(surface.z_range[1], 72.0, abs_tol=1e-12))

    def test_unsafe_surface_expression_is_rejected(self):
        self.assertIsNone(build_science_artifact("Plot 3D z=os.system(x)"))

    def test_implicit_circle_is_sampled_on_the_correct_contour(self):
        artifact = build_science_artifact("Plot x^2 + y^2 = 25")

        self.assertIsNotNone(artifact)
        self.assertEqual(
            artifact.graph.instruction["parameters"]["coordinateSystem"],
            "implicit",
        )
        series = artifact.graph.series[0]
        points = [
            (x, y)
            for x, y in zip(series.x, series.y)
            if math.isfinite(x) and math.isfinite(y)
        ]
        self.assertGreater(len(points), 100)
        maximum_radius_error = max(
            abs(math.hypot(x, y) - 5.0) for x, y in points
        )
        self.assertLess(maximum_radius_error, 0.003)

    def test_piecewise_expression_uses_the_declared_branches(self):
        artifact = build_science_artifact(
            "Plot y=piecewise(x<0, x^2, 2*x+1)"
        )

        series = artifact.graph.series[0]
        left_index = min(
            range(len(series.x)), key=lambda index: abs(series.x[index] + 2.0)
        )
        right_index = min(
            range(len(series.x)), key=lambda index: abs(series.x[index] - 2.0)
        )
        self.assertTrue(
            math.isclose(
                series.y[left_index],
                series.x[left_index] ** 2,
                rel_tol=1e-12,
            )
        )
        self.assertTrue(
            math.isclose(
                series.y[right_index],
                2 * series.x[right_index] + 1,
                rel_tol=1e-12,
            )
        )


class PhysicsConfigurationTests(unittest.TestCase):
    def test_large_elastic_particle_scene_keeps_requested_count(self):
        artifact = build_science_artifact(
            "Create a simulation of 500 particles in a box with elastic collisions and gravity."
        )

        self.assertIsNotNone(artifact)
        self.assertIsNotNone(artifact.physics)
        self.assertEqual(len(artifact.physics.particles), 500)
        self.assertEqual(artifact.physics.restitution, 1.0)
        self.assertEqual(artifact.physics.friction, 1.0)

    def test_projectile_prompt_applies_speed_and_angle(self):
        artifact = build_science_artifact(
            "Simulate a projectile at angle 45 degrees with speed 50."
        )
        particle = artifact.physics.particles[0]

        self.assertEqual(artifact.physics.simulation_type, "projectile-2d")
        self.assertTrue(math.isclose(particle.vx, -particle.vy, rel_tol=1e-6))

    def test_3d_particle_prompt_has_real_depth_state(self):
        artifact = build_science_artifact("Simulate 120 particles in a 3D box with collisions.")

        self.assertEqual(artifact.physics.simulation_type, "particle-3d")
        depth = artifact.physics.instruction["parameters"]["depth"]
        self.assertGreater(depth, 0)
        self.assertTrue(all(0 < particle.z < depth for particle in artifact.physics.particles))
        self.assertTrue(any(abs(particle.vz) > 0 for particle in artifact.physics.particles))

    def test_pendulum_configuration_uses_physical_gravity_and_constraint(self):
        artifact = build_science_artifact(
            "Simulate a pendulum released at angle 30 degrees."
        )

        self.assertEqual(artifact.physics.simulation_type, "pendulum-2d")
        parameters = artifact.physics.instruction["parameters"]
        self.assertTrue(
            math.isclose(parameters["angleRadians"], math.radians(30), rel_tol=1e-12)
        )
        self.assertTrue(math.isclose(parameters["physicalGravity"], 9.81, rel_tol=1e-12))
        self.assertGreater(parameters["length"], 0)

    def test_wave_configuration_is_deterministic_and_sampled(self):
        first = build_science_artifact("Simulate a wave with 64 particles.")
        second = build_science_artifact("Simulate a wave with 64 particles.")

        self.assertEqual(first.physics.simulation_type, "wave-2d")
        self.assertEqual(len(first.physics.particles), 64)
        self.assertEqual(first.physics.particles, second.physics.particles)

    def test_orbit_exposes_2d_and_3d_views_of_one_physical_state(self):
        artifact = build_science_artifact("Simulate 8 objects in orbit.")

        self.assertEqual(artifact.physics.simulation_type, "orbit-2d")
        self.assertEqual(
            artifact.physics.instruction["parameters"]["views"],
            ["2d", "3d"],
        )
        self.assertEqual(len(artifact.physics.particles), 8)

    def test_unsupported_fluid_does_not_masquerade_as_particles(self):
        self.assertIsNone(build_science_artifact("Simulate an SPH fluid in a tank."))


class ModelIdentityTests(unittest.TestCase):
    def test_typo_in_model_question_is_still_handled_locally(self):
        self.assertTrue(wants_model_identity("which moderl are you currently running on boy"))


class MoleculeGeometryTests(unittest.TestCase):
    @staticmethod
    def _angle(first, second):
        first_length = math.sqrt(sum(value * value for value in first))
        second_length = math.sqrt(sum(value * value for value in second))
        cosine = sum(a * b for a, b in zip(first, second)) / (
            first_length * second_length
        )
        return math.degrees(math.acos(max(-1.0, min(1.0, cosine))))

    @staticmethod
    def _outer_vectors(artifact):
        center = artifact.chemistry.atoms[artifact.chemistry.central_atom]
        return [
            (atom.x - center.x, atom.y - center.y, atom.z - center.z)
            for atom in artifact.chemistry.atoms
            if atom.atom_id != artifact.chemistry.central_atom
        ]

    def test_bent_structures_use_their_own_reference_angle(self):
        water = build_molecule_artifact("Show the H2O molecule")
        sulfur_dioxide = build_molecule_artifact("Show the SO2 molecule")

        self.assertTrue(
            math.isclose(
                self._angle(*self._outer_vectors(water)),
                104.5,
                abs_tol=1e-9,
            )
        )
        self.assertTrue(
            math.isclose(
                self._angle(*self._outer_vectors(sulfur_dioxide)),
                119.0,
                abs_tol=1e-9,
            )
        )

    def test_ammonia_coordinates_reproduce_reference_bond_angle(self):
        artifact = build_molecule_artifact("Render the NH3 molecule")
        vectors = self._outer_vectors(artifact)
        pairwise = [
            self._angle(vectors[first], vectors[second])
            for first in range(3)
            for second in range(first + 1, 3)
        ]

        self.assertEqual(artifact.chemistry.coordinate_model, "reference-angle")
        self.assertTrue(
            all(math.isclose(value, 107.0, abs_tol=1e-9) for value in pairwise)
        )

    def test_distorted_t_shape_preserves_reference_angles(self):
        artifact = build_molecule_artifact("Visualize ClF3 molecular geometry")
        vectors = self._outer_vectors(artifact)

        self.assertTrue(
            math.isclose(self._angle(vectors[1], vectors[2]), 175.0, abs_tol=1e-9)
        )
        self.assertTrue(
            math.isclose(self._angle(vectors[0], vectors[1]), 87.5, abs_tol=1e-9)
        )

    def test_instruction_distinguishes_reference_angles_from_coordinate_model(self):
        artifact = build_molecule_artifact("Show the BrF5 molecule")
        parameters = artifact.instruction["parameters"]

        self.assertEqual(parameters["coordinateModel"], "idealized-vsepr")
        self.assertEqual(
            parameters["referenceAnglesDegrees"],
            [84.8, 90.0, 180.0],
        )
        self.assertNotIn("idealAnglesDegrees", parameters)

    def test_unicode_formula_is_recognized(self):
        artifact = build_molecule_artifact("Render H₂O molecular geometry")

        self.assertIsNotNone(artifact)
        self.assertEqual(artifact.chemistry.formula, "H2O")


if __name__ == "__main__":
    unittest.main()
